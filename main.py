import datetime
from requests.models import Response
from telegram import Update, ParseMode
import telegram
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler
import requests
import threading
import time
from telegram.ext.filters import Filters
import json

baseURI = "https://api.sparebank1.no/personal/banking"
accessTokenUri = "https://api-auth.sparebank1.no/oauth/token"
adminIDs = [52507774, 1551390] # Change to your own id(s)
sleepTime = 60

def start_balance_polling(userId):

    refresh_access_token(userId)
    refreshAccessToken = False

    while(True):
        time.sleep(sleepTime)

        data = get_json(userId)

        if refreshAccessToken:
            refresh_access_token(userId)
            refreshAccessToken = False
        else:
            refreshAccessToken = True

        newAccountData = get_account_data(userId)
        if newAccountData != False and newAccountData["availableBalance"] != data["accountDataSnapshot"]["availableBalance"]:
            newTransactionData = get_all_transaction_data(userId)
            if newTransactionData != False and not is_equal_transaction_lists(newTransactionData, data["transactionSnapshot"]):

                data["accountDataSnapshot"] = newAccountData
                data["transactionSnapshot"] = newTransactionData
                write_json(userId, data)
                chat : telegram.Chat
                for chat in data["chats"]:
                    if is_authorized_chat(chat) and str(chat.id) != "-642864988": #TODO remove this
                        try:
                            send_balance_message(chat.id, userId)
                        except:
                            print("ERROR: Could not send automatic message to chat")

def is_equal_transaction_lists(o1, o2):
    # Here we can't just compare the objects because every transaction gets a new ID per api call
    o1Length = len(o1)
    o2Length = len(o2)
    o1FirstAmount = o1[0]["amount"]
    o2FirstAmount = o2[0]["amount"]
    o1LastAmount = o1[o1Length-1]["amount"]
    o2LastAmount = o2[o2Length-1]["amount"]
    return o1Length == o2Length and o1FirstAmount == o2FirstAmount and o1LastAmount == o2LastAmount
    

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


def get_account_data(userId):

    data = get_json(userId)
    accountId = data["accountId"]
    accessToken = data["accessToken"]

    try:
        r : Response = requests.get(f'{baseURI}/accounts/{accountId}', headers={'Authorization': f'Bearer {accessToken}', 'Accept':'application/vnd.sparebank1.v1+json; charset=utf-8'})
        print(f"Response status: {r.status_code}")
        data = r.json()
        validateTest = data["availableBalance"] > -1
        return data
    except:
        return False

def get_transaction_data(userId):
    try:
        return get_all_transaction_data(userId)[0]
    except:
        return False
    
    
def get_all_transaction_data(userId):
    try:
        data = get_json(userId)
        accountId = data["accountId"]
        accessToken = data["accessToken"]

        r : Response = requests.get(f'{baseURI}/transactions?accountKey={accountId}', headers={'Authorization': f'Bearer {accessToken}', 'Accept':'application/vnd.sparebank1.v1+json; charset=utf-8'})
        print(f"Response status: {r.status_code}")
        data = r.json()
        validateTest = data["transactions"][0]["amount"] > 0
        return data["transactions"]
    except:
        return False

def refresh_access_token(userId):
    data = get_json(userId)
    requestBody = {
        'client_id': data['clientId'],
        'client_secret': data['clientSecret'], 
        'refresh_token': data['refreshToken'], 
        'grant_type': 'refresh_token',
    }
    r : Response = requests.post(accessTokenUri, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=requestBody)
    jsonResponse = r.json()
    data['accessToken'] = jsonResponse["access_token"]
    data['refreshToken'] = jsonResponse["refresh_token"]
    write_json(userId, data)
    print(f"New access token status: {r.status_code}")

def send_balance_message(chatId, userId):

    data = get_json(userId)
    accountDataSnapshot = data['accountDataSnapshot']
    transactionSnapshot = data['transactionSnapshot']

    currentBalanceText = f'Current Balance: {accountDataSnapshot["availableBalance"]} {accountDataSnapshot["currencyCode"]}'
    expectedBalanceText = f'Expected Balance: {calculate_expected_balance(userId)} {accountDataSnapshot["currencyCode"]}'
    lastTransactionText = f'Last Transaction: {transactionSnapshot[0]["amount"]} {transactionSnapshot[0]["currencyCode"]}'
    detailsText = f'Details: {transactionSnapshot[0]["description"]}'

    updater.bot.send_message(chatId, f'`{currentBalanceText}\n{expectedBalanceText}\n\n{lastTransactionText}\n{detailsText}\n`', disable_notification = True, parse_mode = ParseMode.MARKDOWN)


def calculate_expected_balance(userId):

    data = get_json(userId)
    payday = data["payday"]
    paydayAmount = data["paydayAmount"]

    now = datetime.datetime.now()
    startYear = now.year
    startMonth = now.month - 1
    if startMonth == 0:
        startMonth = 12
        startYear -= 1
    
    start = datetime.datetime(startYear, startMonth, payday, 0, 0, 0)
    end = datetime.datetime(now.year, now.month, payday, 0, 0, 0)

    if now.day >= payday:
        start = datetime.datetime(now.year, now.month, payday, 0, 0, 0)
        nextmonth = now.month + 1
        year = now.year
        if nextmonth >= 13:
            nextmonth = 1
            year += 1
        end = datetime.datetime(year, nextmonth, payday, 0, 0, 0)

    totalSeconds = (end-start).total_seconds()
    partialSeconds = (end-now).total_seconds()

    return round((partialSeconds * paydayAmount) / totalSeconds, 2)

def added_to_group_handler(update: Update, context: CallbackContext):
    anything_handler(update, context)

def get_json(userId):
    f = open(userId + '.json')
    data = json.load(f)
    f.close()
    return data

def write_json(userId, data):
    with open(userId + ".json", "w") as outfile:
        json.dump(data, outfile)
        outfile.close()


def anything_handler(update: Update, context: CallbackContext):
    userId = is_authorized_chat(update.effective_chat)
    if (userId != False and update.effective_chat != None):
        data = get_json(userId)
        if update.effective_chat not in data["chats"]:
            data["chats"].append(update.effective_chat)
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


def add_semi_admin_handler(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        global add_semi_admin_handler_bool
        add_semi_admin_handler_bool = True
        update.message.reply_text("Share contact to add semi admin")


def refresh(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        global accountDataSnapshot
        accountDataSnapshot = get_account_data()
        global transactionSnapshot 
        transactionSnapshot = get_all_transaction_data()


def get_watchlist_chats(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        data = get_json(str(update.effective_user.id))
        for chat in data['chats']:
            if chat.title:
                update.message.reply_text(f"{chat.title}: {chat.id}")
            elif chat.username:
                update.message.reply_text(f"{chat.username}: {chat.id}")
            else:
                update.message.reply_text(chat.id)


def remove_watch_list_chat_by_id(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        data = get_json(str(update.effective_user.id))
        try:
            id = update.message.text.split(" ")[1]
            for chat in data["chats"]:
                if str(chat.id) == str(id):
                    data["chats"].remove(chat)
                    update.message.reply_text(f"Removed chat with id: {id}")
                    return
        except: 
            print("couldn't remomve chat from watchlist")
    


def help_handler(update: Update, context: CallbackContext):
    update.message.reply_text(f"Use /start to start polling the sparebank-api. If you don't have the tokens and id's, follow this guide: https://developer.sparebank1.no/#/documentation/gettingstarted\n\nCOMMANDS:\n\n/balance : See account balance.\n\n/getWatchListChats : Gets all the chats thats on the watchlist\n\n/removeWatchListChatByID : Removes the watchlist chat by given id")

def start_handler(update: Update, context: CallbackContext):
    try:
        messageArray = update.message.text.split()
        if len(messageArray) > 7:
            userId = str(update._effective_user.id)
            payday = int(messageArray[1])
            paydayAmount = int(messageArray[2])
            accessToken = str(messageArray[3])
            accountId = str(messageArray[4])
            clientId = str(messageArray[5])
            clientSecret = str(messageArray[6])
            refreshToken = str(messageArray[7])

            userObject = {
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
            pollingThread = threading.Thread(name=userId + 'balance_polling_loop', target=start_balance_polling, args=[userId])
            pollingThread.start()
        else:
            update.message.reply_text("Format message like this:\n/start [payday] [paydayAmount] [accessToken] [accountId] [clientId] [clientSecret] [refreshToken]\n\nIf you don't have the tokens and id's, follow this guide: https://developer.sparebank1.no/#/documentation/gettingstarted")
    except:
        update.message.reply_text("Failed to start")


f = open('botConfig.json')
botConfig = json.load(f)
f.close()

updater = Updater(botConfig["apiKey"])

updater.dispatcher.add_handler(CommandHandler('balance', balance_handler))
updater.dispatcher.add_handler(CommandHandler('help', help_handler))
updater.dispatcher.add_handler(CommandHandler('start', start_handler))
updater.dispatcher.add_handler(CommandHandler('getWatchListChats', get_watchlist_chats))
updater.dispatcher.add_handler(CommandHandler('removeWatchListChatByID', remove_watch_list_chat_by_id))
updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'(\S|\s)*'), anything_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, anything_handler))

print("Starting telegram polling...")
updater.start_polling()
updater.idle()