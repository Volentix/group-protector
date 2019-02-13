import json
import traceback
import time
from operator import itemgetter

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

# vtx Defender Initialization
client = MongoClient(connectionString)
db = client.get_default_database()
col_users = db['Users']
col_questions = db['questions']


"""
    Start Quiz
"""
def start_quiz():
    quiz = col_questions.find_one({"Completed": False})

    if quiz is not None:
        reply_markup = [[InlineKeyboardButton(
            text='%s️⃣' % str(int(_id) + 1),
            callback_data='vote|%s|%s' % (quiz['_id'], _id)) for _id in
            range(0, len(quiz['answers']))]]

        text = "<i>Volentix Quiz. What will your choice be?</i>\n\n<b>%s</b>\n\n" \
               "1️⃣ %s \n2️⃣ %s \n3️⃣ %s\n4️⃣ %s\n\n" \
               "<b>To Participate: Users need to push start in</b> %s\n" \
               "<b>Winner</b> will get <b>%s VTX💰</b>" % (
                   quiz['question'],
                   quiz['answers'][0],
                   quiz['answers'][1],
                   quiz['answers'][2],
                   quiz['answers'][3],
                   quiz_bot,
                   win_amount
               )

        bot.send_message(
            quiz_group,
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(reply_markup)
        )
        col_questions.update(
            quiz,
            {
                "$set":
                    {
                        "Status": 1
                    }
            }, upsert=True
        )




def send_announce():
    msg_text = '⏰<b>The Quiz starts in </b>: 1 MINUTE. <b>Everyone prepare.</b>'

    bot.send_message(
        quiz_group,
        msg_text,
        parse_mode='HTML'
    )


def complete_quiz():
    quiz_results = col_questions.find_one({"Status": 1})

    winners = quiz_results[quiz_results['answers'][quiz_results['correct_answer']]]
    winners = sorted(winners, key=itemgetter(2))
    range_tail = 10 if len(winners) > 10 else len(winners)
    if range_tail == 0:
        col_questions.update(
            {
                "Status": 1
            },
            {
                "$set": {
                    quiz_results['answers'][0]: [],
                    quiz_results['answers'][1]: [],
                    quiz_results['answers'][2]: [],
                    quiz_results['answers'][3]: [],
                    "Completed": False,
                    "Winner": None
                }
            }, upsert=True

        )
        bot.send_message(
            quiz_group,
            "🛑<b>No one could answer correctly</b>",
            parse_mode='HTML'
        )
        return

    text = '🏆<b>Quiz completed🏆\nCorrect answer: </b> %s(%s️⃣)\n<b>Winner</b>: <a href="tg://user?id=%s">%s</a> and got %s VTX\n\n🎉<b>Top %s fastest correct answers by</b>:\n' % (
        quiz_results['answers'][quiz_results['correct_answer']], int(quiz_results['correct_answer'])+1, quiz_results['Winner'][0], quiz_results['Winner'][1], win_amount, range_tail
    )
    text += '\n'.join([
        '%s️⃣ <a href="tg://user?id=%s">%s</a>' % (x+1, winners[x][0], winners[x][1]) if x != 9 else '1️⃣ 0️⃣ ' for x in range(0, range_tail)
    ])

    bot.send_message(
        quiz_group,
        text,
        parse_mode='HTML'
    )
    col_questions.update(
        {
            "Status": 1
        },
        {
            "$set":
                {
                    "Completed": True,
                    "Status": 2
                }
        }
    )



send_announce()
time.sleep(60)
start_quiz()
time.sleep(60)
complete_quiz()




