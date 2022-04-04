import datetime
from requests.models import Response
from telegram import Update, ParseMode, chat, message, poll
import telegram
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler
import secrets
import requests
import threading
import time
import re
from telegram.ext.filters import Filters

baseURI = "https://api.sparebank1.no/personal/banking"
bearer = secrets.get_bearer()
accountID = secrets.get_account_id()
adminIDs = [52507774] # Change to your own id(s)
semiAdminIDs = [52507774]
chats = []
accountDataSnapshot = {}
transactionSnapshot = []

payday=15
paydayAmount = 8400


def start_balance_polling():
    global accountDataSnapshot
    global transactionSnapshot

    # Initialize
    accountDataSnapshot = get_account_data()
    transactionSnapshot = get_all_transaction_data()

    while(True):
        time.sleep(120) # Time between each polling of bank API

        accountData = get_account_data()
        if accountData != False and accountData["availableBalance"] != accountDataSnapshot["availableBalance"]:
            transactionData = get_all_transaction_data()
            print(f"New transaction data:\n{transactionData}\n")
            print(f"Transaction data snapshot:\n{transactionSnapshot[0]}\n")
            if transactionData != False and not is_equal_transactions(transactionData, transactionSnapshot):

                accountDataSnapshot = accountData
                transactionSnapshot = transactionData
                chat : telegram.Chat
                for chat in chats:
                    if is_authorized_chat(chat):
                        try:
                            send_balance_message(chat.id)
                        except:
                            print("ERROR: Could not send automatic message to chat. Is the bot a member in the chat?")

def is_equal_transactions(o1, o2):
    print(o1)
    print(o2)
    return o1 == o2
    

def balance_handler(update: Update, context: CallbackContext) -> None:
    try:
        if is_semi_authorized_user(update.effective_user.id) or is_authorized_chat(update.effective_chat):
            send_balance_message(update.effective_chat.id)
        else:
            update.message.reply_text("Unauthorized")
    except:
        print("ERROR: Could not send manual balance message to chat")


def get_account_data():
    try:
        r : Response = requests.get(f'{baseURI}/accounts/{accountID}', headers={'Authorization': f'Bearer {bearer}', 'Content-Type': 'application/vnd.sparebank1.v5+json', 'Accept':'application/vnd.sparebank1.v5+json'})
        print(f"Response status: {r.status_code}")
        data = r.json()
        validateTest = data["availableBalance"] > -1
        return data
    except:
        return False

def get_transaction_data():
    try:
        return get_all_transaction_data()[0]
    except:
        return False
    
    
def get_all_transaction_data():
    try:
        r : Response = requests.get(f'{baseURI}/transactions?accountKey={accountID}', headers={'Authorization': f'Bearer {bearer}', 'Content-Type': 'application/vnd.sparebank1.v1+json', 'Accept':'application/vnd.sparebank1.v1+json'})
        print(f"Response status: {r.status_code}")
        data = r.json()
        validateTest = data["transactions"][0]["amount"] > 0
        return data["transactions"]
    except:
        return False


def send_balance_message(chatId):

    currentBalanceText = f'Current Balance: {accountDataSnapshot["availableBalance"]} {accountDataSnapshot["currencyCode"]}'
    expectedBalanceText = f'Expected Balance: {calculate_expected_balance()} {accountDataSnapshot["currencyCode"]}'
    lastTransactionText = f'Last Transaction: {transactionSnapshot[0]["amount"]} {transactionSnapshot[0]["currencyCode"]}'
    #date = f'Date: {datetime.utcfromtimestamp(transactionSnapshot[0]["date"]).strftime("%Y-%m-%d %H:%M")}'
    detailsText = f'Details: {transactionSnapshot[0]["description"]}'

    updater.bot.send_message(chatId, f'`{currentBalanceText}\n{expectedBalanceText}\n\n{lastTransactionText}\n{detailsText}\n`', disable_notification = True, parse_mode = ParseMode.MARKDOWN)


def calculate_expected_balance():
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
    for member in update.message.new_chat_members:
        if member.username == secrets.get_bot_username():
            addchat_handler(update, context)


def stop_handler(update: Update, context: CallbackContext):

    if is_authorized_user(update.effective_user.id):
        update.message.reply_text("Shutting down...")
        updater.stop()



def addchat_handler(update: Update, context: CallbackContext):
    if (update.effective_chat not in chats):
        chats.append(update.effective_chat)
        print("Added to watchlist!")
    else:
        print("Chat already in watchlist!")
    updater.bot.deleteMessage(update.effective_chat.id, update.message.message_id)



def is_authorized_chat(chat : telegram.Chat):

    for adminId in adminIDs:
        try:
            if chat.get_member(adminId).user.username != "":
                print(f"Groupchat: {chat.title} is Authorized")
                return True
        except:
            return False

    print(f"Groupchat: {chat.title} is Unauthorized")
    return False
    

def is_authorized_user(id):
    return id in adminIDs

def is_semi_authorized_user(id):
    return is_authorized_user(id) or id in semiAdminIDs


global add_semi_admin_handler_bool
add_semi_admin_handler_bool = False

global set_expected_balance_amount_handler_bool
set_expected_balance_amount_handler_bool = False

global set_payday_bool
set_payday_bool = False


def set_payday(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        global set_payday_bool
        set_payday_bool = True
        update.message.reply_text(f"Current payday: {payday}\nSet the payday of the month:")


def add_semi_admin_handler(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        global add_semi_admin_handler_bool
        add_semi_admin_handler_bool = True
        update.message.reply_text("Share contact to add semi admin")


def set_expected_balance_handler(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        global set_expected_balance_amount_handler_bool
        set_expected_balance_amount_handler_bool = True
        update.message.reply_text(f"Current max balance: {paydayAmount} NOK\nSend new expected max balance:")


def number_handler(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        global set_expected_balance_amount_handler_bool
        global paydayAmount
        global set_payday_bool
        global payday
        if set_expected_balance_amount_handler_bool:
            set_expected_balance_amount_handler_bool = False
            matches = re.findall(r"[0-9]+", update.message.text)
            if len(matches) > 0:
                paydayAmount = int(matches[0])
            update.message.reply_text(f"Updated current max balance: {paydayAmount} NOK")

        elif set_payday_bool:
            set_payday_bool = False
            matches = re.findall(r"[0-9]+", update.message.text)
            if len(matches) > 0:
                x = int(matches[0])
                if x <= 28 and x >= 0:
                    payday = x
            update.message.reply_text(f"Updated current payday: {payday}")


def contact_handler(update: Update, context: CallbackContext):
    global add_semi_admin_handler_bool
    if is_authorized_user(update.effective_user.id) and add_semi_admin_handler_bool:
        if update.effective_user.id not in semiAdminIDs:
            semiAdminIDs.append(update.message.contact.user_id)
        add_semi_admin_handler_bool = False
        update.message.reply_text(f"Added {update.message.contact.first_name} as semi admin")


def get_watchlist_chats(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        for chat in chats:
            if chat.title:
                update.message.reply_text(f"{chat.title} - {chat.id}")
            elif chat.username:
                update.message.reply_text(f"{chat.username} - {chat.id}")
            else:
                update.message.reply_text(chat.id)


def remove_watch_list_chat_by_id(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        try:
            id = update.message.text.split(" ")[1]
            for chat in chats:
                print(chat.id)
                print(id)
                if str(chat.id) == str(id):
                    chats.remove(chat)
                    update.message.reply_text(f"Removed chat with id: {id}")
                    return
        except: 
            print("couldn't remomve chat from watchlist")
    


def help_handler(update: Update, context: CallbackContext):
    update.message.reply_text(f"/balance : See account balance.\n\n/stop : Stop the bot.\n\n/addToWatchList : Add the current chat to list that gets balance updates.\n\n/addSemiAdmin : Give rights to someone to use the bot outside of an authorized chat\n\n/setExpectedBalanceAmount : Set the realistic max amount the account will have on the payday\n\n/setPayday : set the day the account gets filled and the countdown starts again\n\n/getWatchListChats : Gets all the chats thats on the watchlist\n\n/removeWatchListChatByID : Removes the watchlist chat by given id")


updater = Updater(secrets.get_telegram_api_key())

updater.dispatcher.add_handler(CommandHandler('balance', balance_handler))
updater.dispatcher.add_handler(CommandHandler('stop', stop_handler))
updater.dispatcher.add_handler(CommandHandler('help', help_handler))
updater.dispatcher.add_handler(CommandHandler('start', help_handler))
updater.dispatcher.add_handler(CommandHandler('addToWatchList', addchat_handler))
updater.dispatcher.add_handler(CommandHandler('addSemiAdmin', add_semi_admin_handler))
updater.dispatcher.add_handler(CommandHandler('setExpectedBalanceAmount', set_expected_balance_handler))
updater.dispatcher.add_handler(CommandHandler('setPayday', set_payday))
updater.dispatcher.add_handler(CommandHandler('getWatchListChats', get_watchlist_chats))
updater.dispatcher.add_handler(CommandHandler('removeWatchListChatByID', remove_watch_list_chat_by_id))
updater.dispatcher.add_handler(MessageHandler(Filters.contact, contact_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, added_to_group_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'[0-9]'), number_handler))

pollingThread = threading.Thread(name='balance_polling_loop', target=start_balance_polling)
pollingThread.start()

print("Starting telegram polling...")
updater.start_polling()
updater.idle()