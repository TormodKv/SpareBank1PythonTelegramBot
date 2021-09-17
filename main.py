from requests.models import Response
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
    dataSnapshot = get_account_data(accountID)
    while(True):
        time.sleep(100) # Time between each polling of bank API
        data = get_account_data(accountID)
        if data != False and data["balance"]["amount"] != dataSnapshot["balance"]["amount"]:
            dataSnapshot = data
            chat : telegram.Chat
            for chat in chats:
                if is_authorized_chat(chat):
                    try:
                        updater.bot.send_message(chat.id, f'Updated Balance: {data["balance"]["amount"]} {data["balance"]["currencyCode"]}', disable_notification = True)
                    except:
                        print("ERROR: Could not send automatic message to chat. Is the bot a member in the chat?")


def balance_handler(update: Update, context: CallbackContext) -> None:

    try:
        if is_semi_authorized_user(update.effective_user.id) or is_authorized_chat(update.effective_chat):
            update.message.reply_text(f'Balance: {dataSnapshot["balance"]["amount"]} {dataSnapshot["balance"]["currencyCode"]}')
        else:
            update.message.reply_text("Unauthorized")
    except:
        print("ERROR: Could not send manual message to chat")


def get_account_data(id):
    try:
        r : Response = requests.get(f'{baseURI}/accounts/{id}', headers={'Authorization': f'Bearer {bearer}'})
        print(f"Response status: {r.status_code}")
        data = r.json()
        validateTest = data["balance"]["amount"]
        return data
    except:
        return False


def added_to_group_handler(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if member.username == secrets.get_bot_username():
            chats.append(update.effective_chat)


def stop_handler(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        updater.stop()
        import sys
        sys.exit()


def addchat_handler(update: Update, context: CallbackContext):
    chats.append(update.effective_chat)
    print("Added to watchlist!")


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
add_semi_admin_handler_bool = True


def add_semi_admin_handler(update: Update, context: CallbackContext):
    if is_authorized_user(update.effective_user.id):
        global add_semi_admin_handler_bool
        add_semi_admin_handler_bool = True
        update.message.reply_text("Share contact to add semi admin")


def contact_handler(update: Update, context: CallbackContext):
    global add_semi_admin_handler_bool
    if is_authorized_user(update.effective_user.id) and add_semi_admin_handler_bool:
        if update.effective_user.id not in semiAdminIDs:
            semiAdminIDs.append(update.message.contact.user_id)
        add_semi_admin_handler_bool = False
        update.message.reply_text(f"Added {update.message.contact.first_name} as semi admin")


def help_handler(update: Update, context: CallbackContext):
    update.message.reply_text(f"/balance : See account balance.\n\n/stop : Stop the bot.\n\n/addToWatchList : Add the current chat to list that gets balance updates.\n\n/addSemiAdmin : Give rights to someone to use the bot outside of an authorized chat")


updater = Updater(secrets.get_telegram_api_key())

updater.dispatcher.add_handler(CommandHandler('balance', balance_handler))
updater.dispatcher.add_handler(CommandHandler('stop', stop_handler))
updater.dispatcher.add_handler(CommandHandler('help', help_handler))
updater.dispatcher.add_handler(CommandHandler('start', help_handler))
updater.dispatcher.add_handler(CommandHandler('addToWatchList', addchat_handler))
updater.dispatcher.add_handler(CommandHandler('addSemiAdmin', add_semi_admin_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.contact, contact_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, added_to_group_handler))

t = threading.Thread(name='balance_polling_loop', target=start_balance_polling)
t.start()

print("Starting telegram polling...")
updater.start_polling()
updater.idle()