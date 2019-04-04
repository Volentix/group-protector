import json

import datetime
from pymongo import MongoClient
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton

with open('services.json') as conf_file:
    conf = json.load(conf_file)
    connectionString = conf['mongo']['connectionString']
    bot_token = conf['telegram_bot']['bot_token']
    questions = conf['questions']
    quiz_bot = conf['quiz_bot']
    win_amount = conf['win_amount']
    quiz_group = conf['quiz_group']



bot = Bot(bot_token)


# MongoDB initialization
client = MongoClient(connectionString)
db = client.get_default_database()
col_users = db['Users']
col_questions = db['questions']


"""
    Calculate timeleft and send rules to the community
"""
def send_timeleft():
    print(datetime.datetime.now())
    if datetime.datetime.now() < datetime.datetime.now().replace(hour=14):
        time_release = datetime.datetime.now().replace(hour=14, minute=0, second=0)

    elif datetime.datetime.now() > datetime.datetime.now().replace(hour=14):
        time_release = (datetime.datetime.now() + datetime.timedelta(days=1)).replace(hour=14, minute=0, second=0)
    timeleft = time_release - datetime.datetime.now()
    print(timeleft)

    days, seconds = timeleft.days, timeleft.seconds
    hours = days * 24 + seconds // 3600
    minutes = (seconds % 3600) // 60

    msg_text = '🏆<b>Welcome to the Volentix Daily Quiz!</b>🏆\n<b>Are you ready?</b>\n\n<b>Be the fastest to answer correctly and win VTX!</b>\n📜 Quiz Rules:\n📌 Fastest correct answer wins\n📌 Start %s bot\n\n<b>For withdrawal:</b>\n📌 Must have Verto Wallet\n📌 Must KYC to get VTX\n\n<i>You can check your balance in </i>%s <i>bot using /balance command</i>\n\nGood luck!\n⏰<b>The Quiz starts in </b>: %s hours %s minutes' % (
        quiz_bot,
        quiz_bot,
        hours,
        minutes
    )

    bot.send_message(
        quiz_group,
        msg_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="📍Start bot to participate📍",
                            url="https://t.me/vtxprotector_bot"
                        )
                    ]
                ])
    )

send_timeleft()