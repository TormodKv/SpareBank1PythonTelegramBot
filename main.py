from telegram import Update
import telegram
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler
import secrets
import requests
import threading
import time
from telegram.ext.filters import Filters

baseURI = "https://api.sparebank1.no/open/personal/banking"
bearer = secrets.get_bearer()
accountID = secrets.get_account_id()
adminIDs = [52507774] # Change to your own id(s)
semiAdminIDs = [52507774]
chats = []
dataSnapshot = {}

def start_balance_polling():
    global dataSnapshot
    #dataSnapshot = get_account_data(accountID)
    while(True):
        time.sleep(60) # Time between each polling of bank API
        data = get_account_data(accountID)
        if data != False and data["balance"]["amount"] != dataSnapshot["balance"]["amount"]:
            dataSnapshot = data
            chat : telegram.Chat
            for chat in chats:
                if is_authorized_chat(chat):
                    try:
                        updater.bot.send_message(chat.id, f'Balance: {data["balance"]["amount"]} {data["balance"]["currencyCode"]}', disable_notification = True)
                    except:
                        print("ERROR: Could not send automatic message to chat")


def balance_handler(update: Update, context: CallbackContext) -> None:
    try:
        update.message.reply_text(f'Balance: {dataSnapshot["balance"]["amount"]} {dataSnapshot["balance"]["currencyCode"]}')
    except:
        print("ERROR: Could not send manual message to chat")


def get_account_data(id):
    try:
        r = requests.get(f'{baseURI}/accounts/{id}', headers={'Authorization': f'Bearer {bearer}'})
        data = r.json()
        validateTest = data["balance"]["amount"]
        return data
    except:
        return False


def added_to_group_handler(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if member.username == 'SpareBank1bot':
            chats.append(update.effective_chat)
            is_authorized_chat(update.effective_chat)


def is_authorized_chat(chat : telegram.Chat):

    for adminId in adminIDs:
        if chat.get_member(adminId) != None:
            print(f"Groupchat: {chat.title} is Authorized")
            return True

    print(f"Groupchat: {chat.title} is Unauthorized")
    return False


updater = Updater(secrets.get_telegram_api_key())

updater.dispatcher.add_handler(CommandHandler('balance', balance_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, added_to_group_handler))

t = threading.Thread(name='balance_polling_loop', target=start_balance_polling)
t.start()

print("Starting telegram polling...")
updater.start_polling()
updater.idle()