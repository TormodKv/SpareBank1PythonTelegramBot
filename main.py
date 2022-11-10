import os
import socket
import sys
from requests.models import Response
from telegram import Update, ParseMode
import telegram
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler
import requests
import threading
import time
from telegram.ext.filters import Filters
import json
from datetime import datetime

baseURI = "https://api.sparebank1.no/personal/banking"
accessTokenUri = "https://api-auth.sparebank1.no/oauth/token"
adminIDs = [52507774, 1551390] # Change to your own id(s)
sleepTime = 200

def start_balance_polling(userId):

    restartApp = False

    # Get fresh refresh token
    data = refresh_access_token(userId)
    refreshAccessToken = False

    # Ensure that data is not False and is retrieved correctly
    data["accountDataSnapshot"] = False
    data["transactionSnapshot"] = False

    while data["accountDataSnapshot"] == False :
        data["accountDataSnapshot"] = get_account_data(userId, data)
        time.sleep(10)

    while data["transactionSnapshot"] == False :
        data["transactionSnapshot"] = get_all_transaction_data(userId, data)
        time.sleep(10)

    write_json(userId, data)

    # Polling loop
    while True:
        time.sleep(sleepTime)

        if not internet(): 
            restartApp = True
            continue

        if restartApp:
            restart()

        data = {}

        if refreshAccessToken:
            data = refresh_access_token(userId)
            refreshAccessToken = False
            time.sleep(20)
        else:
            refreshAccessToken = True
            data = data = get_json(userId)

        newAccountData = get_account_data(userId, data)

        if newAccountData == False: continue

        #This is totally unnecessary 🤷‍♂️
        if data["accountDataSnapshot"]["owner"]["age"] != newAccountData["owner"]["age"]:
            for chat in data["chats"]:
                try:
                    send_birthday_message(chat, userId, data)
                except:
                    print("ERROR: Could not send automatic birthdaymessage 🎈 to chat: " + str(chat))

        if newAccountData["availableBalance"] == data["accountDataSnapshot"]["availableBalance"]: continue

        newTransactionData = get_all_transaction_data(userId, data)

        if newTransactionData == False or is_equal_transaction_lists(newTransactionData, data["transactionSnapshot"]): continue

        data["accountDataSnapshot"] = newAccountData
        data["transactionSnapshot"] = newTransactionData
        write_json(userId, data)
        for chat in data["chats"]:
            try:
                send_balance_message(chat, userId, data)
            except:
                print("ERROR: Could not send automatic message to chat: " + str(chat))

def restart():
    print("----------------------------")
    print(" - Restarting application - ")
    print("----------------------------")
    os.execl(sys.executable, os.path.abspath(__file__), *sys.argv)

def is_equal_transaction_lists(o1, o2):
    # Here we can't just compare the objects because every transaction gets a new ID per api call
    if len(o1) != len(o2):
        return False

    for i in range(len(o1)):
        if o1[i]["amount"] != o2[i]["amount"]:
            return False

    return True
    

def balance_handler(update: Update, context: CallbackContext) -> None:
    try:
        adminId = is_authorized_chat(update.effective_chat)
        if adminId == False:
            adminId = update.effective_user.id

        if is_authorized_user(adminId):
            send_balance_message(update.effective_chat.id, adminId)
        else:
            update.message.reply_text("Unauthorized")
    except:
        print("ERROR: Could not send manual balance message to chat")


def get_account_data(userId: str, passedData : object | None = None):

    data = get_json(userId, passedData)
    accountId = data["accountId"]
    accessToken = data["accessToken"]

    try:
        r : Response = req("get",f'{baseURI}/accounts/{accountId}', 
            headers={'Authorization': f'Bearer {accessToken}', 'Accept': 'application/vnd.sparebank1.v5+json; charset=utf-8'}
        )

        print(f"Get account data status: {r.status_code}")
        data = r.json()
        validateTest = data["availableBalance"] > -1
        return data
    except:
        return False
    
def get_all_transaction_data(userId: str, passedData : object | None = None):
    try:
        data = get_json(userId, passedData)
        accountId = data["accountId"]
        accessToken = data["accessToken"]

        r : Response = req("get", f'{baseURI}/transactions?accountKey={accountId}', 
            headers={'Authorization': f'Bearer {accessToken}', 'Accept': 'application/vnd.sparebank1.v1+json; charset=utf-8'}
        )
        print(f"Get transactions status: {r.status_code}")
        data = r.json()
        validateTest = data["transactions"][0]["amount"] > 0
        data = data["transactions"]
        partions = []
        interval = len(data)//10
        i = 0
        while i + 1 < len(data):
            partions.append(data[i])
            i += interval
        return partions
    except:
        return False

def refresh_access_token(userId: str, passedData : object | None = None):
    r = {"Message": "Response object initialized"}
    try:
        data = get_json(userId, passedData)
        requestBody = {
            'client_id': data['clientId'],
            'client_secret': data['clientSecret'], 
            'refresh_token': data['refreshToken'], 
            'grant_type': 'refresh_token',
        }
        r : Response = req("post", accessTokenUri, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=requestBody)
        jsonResponse = r.json()
        data['accessToken'] = jsonResponse["access_token"]
        data['refreshToken'] = jsonResponse["refresh_token"]
        write_json(userId, data)
        print(f"New access token status: {r.status_code}")
        return data
    except:
        print("Couldn't get refresh token. \nResponse:")
        print(r)

def send_balance_message(chatId, userId: str, passedData : object | None = None):

    data = get_json(userId, passedData)
    accountDataSnapshot = data['accountDataSnapshot']
    transactionSnapshot = data['transactionSnapshot']

    currentBalanceText = f'Current Balance: {accountDataSnapshot["availableBalance"]} {accountDataSnapshot["currencyCode"]}'
    expectedBalanceText = f'Expected Balance: {calculate_expected_balance(userId, data)} {accountDataSnapshot["currencyCode"]}'
    lastTransactionText = f'Last Transaction: {transactionSnapshot[0]["amount"]} {transactionSnapshot[0]["currencyCode"]}'
    detailsText = f'Details: {transactionSnapshot[0]["description"]}'

    updater.bot.send_message(chatId, f'`{currentBalanceText}\n{expectedBalanceText}\n\n{lastTransactionText}\n{detailsText}\n`', disable_notification = True, parse_mode = ParseMode.MARKDOWN)

def send_birthday_message(chatId, userId: str, passedData : object | None = None):
    data = get_json(userId, passedData)
    updater.bot.send_message(chatId, f'Happy Birthday {data["accountDataSnapshot"]["owner"]["name"]}! 🎈')

def calculate_expected_balance(userId: str, passedData : object | None = None):

    data = get_json(userId, passedData)
    payday = data["payDay"]
    paydayAmount = data["paydayAmount"]

    now = datetime.now()
    startYear = now.year
    startMonth = now.month - 1
    if startMonth == 0:
        startMonth = 12
        startYear -= 1
    
    start = datetime(startYear, startMonth, payday, 0, 0, 0)
    end = datetime(now.year, now.month, payday, 0, 0, 0)

    if now.day >= payday:
        start = datetime(now.year, now.month, payday, 0, 0, 0)
        nextmonth = now.month + 1
        year = now.year
        if nextmonth >= 13:
            nextmonth = 1
            year += 1
        end = datetime(year, nextmonth, payday, 0, 0, 0)

    totalSeconds = (end-start).total_seconds()
    partialSeconds = (end-now).total_seconds()

    return round((partialSeconds * paydayAmount) / totalSeconds, 2)

def added_to_group_handler(update: Update, context: CallbackContext):
    anything_handler(update, context)

def get_json(userId: str, passedData : object | None = None):

    if passedData != None:
        return passedData
    try:
        f = open(str(userId) + '.json')
        data = json.load(f)
        f.close()
        if len(data["refreshToken"]) > 0:
            print("JSON file read")
            return data
        return None
    except:
        return None

def write_json(userId, data):
    with open(str(userId) + ".json", "w") as outfile:
        json.dump(data, outfile)
        outfile.close()


def anything_handler(update: Update, context: CallbackContext):
    userId = is_authorized_chat(update.effective_chat)
    if (userId != False and update.effective_chat != None):
        data = get_json(str(userId))
        if update.effective_chat.id not in data["chats"]:
            data["chats"].append(update.effective_chat.id)
            write_json(userId, data)
            print("Added to watchlist! (by message)")


def is_authorized_chat(chat : telegram.Chat):

    for adminId in adminIDs:
        try:
            if chat.get_member(adminId).user.username != "":
                print(f"Groupchat: {chat.title} is Authorized")
                return adminId
        except:
            continue

    print(f"Groupchat: {chat.title} is Unauthorized")
    return False
    

def is_authorized_user(id):
    return id in adminIDs


global add_semi_admin_handler_bool
add_semi_admin_handler_bool = False

global set_expected_balance_amount_handler_bool
set_expected_balance_amount_handler_bool = False


def get_watchlist_chats(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        data = get_json(str(update.effective_user.id))
        for chat in data['chats']:
            update.message.reply_text(f"{chat}")


def remove_watch_list_chat_by_id(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        data = get_json(str(update.effective_user.id))
        try:
            id = update.message.text.split(" ")[1]
            for chat in data["chats"]:
                if str(chat) == str(id):
                    data["chats"].remove(chat)
                    update.message.reply_text(f"Removed chat with id: {id}")
                    write_json(str(update.effective_user.id), data)
                    return
        except: 
            print("couldn't remomve chat from watchlist")
    


def help_handler(update: Update, context: CallbackContext):
    update.message.reply_text(f"Use /start to start polling the sparebank-api. If you don't have the tokens and id's, follow this guide: https://developer.sparebank1.no/#/documentation/gettingstarted\n\nCOMMANDS:\n\n/balance : See account balance.\n\n/getWatchListChats : Gets all the chats thats on the watchlist\n\n/removeWatchListChatByID : Removes the watchlist chat by given id")

def thread_exist(userId):
    threadExist = False
    for thread in threading.enumerate(): 
        if thread.name == str(userId) + 'balance_polling_loop':
            threadExist = True
            break
    return threadExist

def start_polling_thread(userId):
    if not thread_exist(userId):
        pollingThread = threading.Thread(name=str(userId) + 'balance_polling_loop', target=start_balance_polling, args=[userId])
        pollingThread.start()
    else:
        print("Thread for user: " + str(userId) + " already exist")

def start_handler(update: Update, context: CallbackContext):
    try:
        userId = str(update._effective_user.id)
        if thread_exist(userId):
            update.message.reply_text("Thread already exist")
            return

        messageArray = update.message.text.split()
        if len(messageArray) > 7:
            payday = int(messageArray[1])
            paydayAmount = int(messageArray[2])
            accessToken = "Not yet initialized" #We don't actually need the access token because we have the refreshtoken 😉
            accountId = str(messageArray[3])
            clientId = str(messageArray[4])
            clientSecret = str(messageArray[5])
            refreshToken = str(messageArray[6])

            userObject = {
                "userId": userId,
                "payDay": payday,
                "paydayAmount": paydayAmount,
                "accountId" : accountId,
                "clientId" : clientId,
                "clientSecret" : clientSecret,
                "refreshToken": refreshToken,
                "chats": [],
                "accountDataSnapshot": {},
                "transactionSnapshot": [],
                "accessToken": accessToken,
            }
    
            write_json(userId, userObject)
            start_polling_thread(userId)
        else:
            update.message.reply_text("Format message like this:\n/start \n[payday] \n[paydayAmount] \n[accountId] \n[clientId] \n[clientSecret] \n[refreshToken]\n\nIf you don't have the tokens and id's, follow this guide: https://developer.sparebank1.no/#/documentation/gettingstarted")
    except:
        update.message.reply_text("Failed to start")


def get_bot_config(): 
    f = open('botConfig.json')
    botConfig = json.load(f)
    f.close()
    return botConfig

def req(method: str = "get", url: str = "", headers: object = {}, data: object = {}):
    if not internet():
        return False
    time.sleep(5) #Might be required. Idk why 🤷‍♂️
    if method == "get":
        return requests.get(url, headers=headers, data=data)
    if method == "post":
        return requests.post(url, headers=headers, data=data)
    return False


def internet(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error as ex:
        print("Connection refused. You're offline. Time: " + str(datetime.now().strftime("%H:%M:%S  %Y.%m.%d")))
        return False

def auto_start_threads():
    for admin in adminIDs:
        if get_json(str(admin)) != None:
            start_polling_thread(str(admin))

updater = Updater(get_bot_config()["apiKey"])

updater.dispatcher.add_handler(CommandHandler('balance', balance_handler))
updater.dispatcher.add_handler(CommandHandler('help', help_handler))
updater.dispatcher.add_handler(CommandHandler('start', start_handler))
updater.dispatcher.add_handler(CommandHandler('getWatchListChats', get_watchlist_chats))
updater.dispatcher.add_handler(CommandHandler('removeWatchListChatByID', remove_watch_list_chat_by_id))
updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'(\S|\s)*'), anything_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, anything_handler))

auto_start_threads()

print("Starting telegram polling...")
updater.start_polling()
updater.idle()