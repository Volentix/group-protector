import json
import traceback
import datetime
import re
from bson import ObjectId
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
    faq_data = conf['faq']


REGEX = "(работ|бесплат|airdrop|програм|канал|подпис|асик|реклама|продаж|прода|куплю|обмен)|([a-zA-Z]+\.)+[a-zA-Z]+|http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
REGEX_ALL = "(https://t\.me/)|(t\.me/joinchat/)|(telegram\.me/)"
BROADCAST_CHANNEL = '-1001248917216'
WELCOME_MESSAGE = """
<b>Welcome to the VTX Telegram group!</b>\n\nNow you can interact with users in our telegram group @Volentix. Don't forget to read our <a href="t.me/Volentix/11027">pinned message</a> 
"""


class Defender:

    def __init__(self):
        # INIT
        self.bot = Bot(bot_token)

        # vtx Defender Initialization
        client = MongoClient(connectionString)
        db = client.get_default_database()
        self.col_captcha = db['captcha']
        self.col_users = db['Users']
        self.spam_msgs_collection = db['spam']
        self.pending_msgs_collection = db['pending_messages']
        self.users_whitelist = db['whitelist']
        self.col_questions = db['questions']

        # processing captchas
        self.captcha_processing()

        # get chat updates
        self.new_message = self.wait_new_message()
        self.message = self.new_message.message \
            if self.new_message.message is not None \
            else self.new_message.callback_query.message
        self.text, _is_document = self.get_action(self.new_message)
        self.message_text = str(self.text).lower()
        print(self.text)

        # init user data
        try:
            self.first_name = self.new_message.effective_user.first_name
            self.username = self.new_message.effective_user.username
            self.user_id = self.new_message.effective_user.id
        except Exception as exc:
            print(exc)

        try:
            self._is_verified = self.col_users.find_one({"_id": self.user_id})[
                'IsVerified']
        except Exception as exc:
            print(exc)
            self._is_verified = True


        print(self.username)
        print(self.user_id)
        print(self.first_name)
        print(self.message_text, '\n\n')
        self.group_id = self.message.chat.id

        self.action_processing()

        if 'group' in self.message.chat.type:
            # parse user_info
            self.group_username = self.get_group_username()

            _is_whitelist_user = False
            for _x in list(self.users_whitelist.find()):
                try:
                    if str(_x['key']).lower() in str(
                            self.message.from_user).lower():
                        _is_whitelist_user = True
                except Exception as exc:
                    print(exc)

            if not _is_whitelist_user and _is_document:
                self.bot.delete_message(chat_id=self.group_id,
                                        message_id=self.message.message_id)

            # init group collection
            if not self._is_verified:
                # check msg on spam
                if not self._is_msg_spam():
                    self.save_unverified_msg()
                self.bot.delete_message(chat_id=self.group_id,
                                        message_id=self.message.message_id)
                self.send_captcha(self.first_name, self.user_id)

            elif not _is_whitelist_user:
                self.check_whitelist()

    """
        This method save msg of unverified user with target to send it again, if user will auth.
    """

    def save_unverified_msg(self):
        try:
            # forward msg to PM(Own Account to avoid spam of all admins)
            a = self.bot.forward_message(
                MY_ID,
                self.group_id,
                message_id=self.message.message_id
            )

            # Add msg_id, group_id, user_id, datetime into db to define specified msg of users.
            self.pending_msgs_collection.update(
                {
                    "_id": a.message_id
                },
                {
                    "$set": {
                        "_id": a.message_id,
                        "group_id": self.group_id,
                        "user_id": self.user_id,
                        "Datetime": datetime.datetime.now()
                    }
                }, upsert=True
            )
        except Exception as exc:
            print(exc)

    """
        Check if user's msg is spam
    """

    def check_whitelist(self):
        # Receive admin list
        admin_list = self.get_admin_list()

        # check is this user exists in admin's list
        _is_user_admin = str(self.user_id) in admin_list

        if not _is_user_admin:
            self.check_admin_commands(_is_user_admin)


    def check_admin_commands(self, _is_user_admin):

        if _is_user_admin and "/ban" == str(self.message_text) and \
                        self.message.reply_to_message is not None:
            user_to_ban_id = self.message.reply_to_message.from_user.id
            reply_message_id = self.message.reply_to_message.message_id
            self.bot.delete_message(chat_id=self.group_id,
                                    message_id=reply_message_id)
            self.bot.kick_chat_member(chat_id=self.group_id,
                                      user_id=user_to_ban_id)
            self.bot.delete_message(chat_id=self.group_id,
                                    message_id=self.message.message_id)
            self.bot.send_message(BROADCAST_CHANNEL,
                                  "Group: @%s\n"
                                  "USER %s BANNED BY USER: %s" % (
                                      self.group_username,
                                      self.message.reply_to_message. \
                                          from_user.username,
                                      self.username)
                                  )
        elif _is_user_admin and "/mute" in str(self.message_text) and \
                        self.message.reply_to_message is not None and \
                        len(self.message_text.split(' ')) > 0:
            timestamp_now = datetime.datetime.now().timestamp()
            user_date = int(self.message_text.split(' ')[1])
            until_date = timestamp_now + \
                         datetime.timedelta(days=
                                            user_date).total_seconds()
            user_to_ban_id = self.message.reply_to_message.from_user.id
            reply_message_id = self.message.reply_to_message.message_id
            self.bot.delete_message(chat_id=self.group_id,
                                    message_id=reply_message_id)
            self.bot.restrict_chat_member(
                chat_id=self.group_id,
                user_id=user_to_ban_id,
                until_date=until_date
            )
            self.bot.send_message(self.group_id,
                                  text='<i>User muted for a %s day(s)!</i>' %
                                       (str(user_date)),
                                  parse_mode='HTML')
            self.bot.send_message(BROADCAST_CHANNEL,
                                  "Group: @%s\n"
                                  "USER %s Muted BY USER: %s" % (
                                      self.group_username,
                                      self.message.reply_to_message. \
                                          from_user.username,
                                      self.username)
                                  )


        else:
            if not _is_user_admin:
                matches = re.search(REGEX_ALL, self.message_text)
                if matches is not None:
                    #    self.restrict_user()
                    self.bot.delete_message(self.group_id,
                                            self.message.message_id)
                    # print("Check_message: %s" % matches.groups())
                    self.bot.send_message(BROADCAST_CHANNEL,
                                          "Group: @%s\n"
                                          "USER SPAM "
                                          "MESSAGE: %s"
                                          "\nUsername: %s\n%s" % (
                                              self.group_username,
                                              matches.groups(),
                                              self.username,
                                              self.message_text)
                                          )

            self.new_users = self.message.new_chat_members
            _is_new_users = len(self.message.new_chat_members) > 0

            _db_user = self.col_users.find_one(
                {"_id": self.user_id})
            _is_user_in_collection = _db_user is not None
            _is_forward = self.message.forward_from is not None
            _is_chat_forward = self.message.forward_from_chat is not None
            _is_document = self.message.document is not None
            _is_photo = len(self.message.photo) > 0

            # Reason Forward Messages from chat or users
            if not _is_user_admin and (_is_chat_forward or _is_forward):
                try:
                    _user_join_date = _db_user['JoinDate']
                    _is_join_long_time_ago = datetime.datetime.now() - \
                                             datetime.timedelta(days=20) \
                                             > _user_join_date
                    if not _is_join_long_time_ago:
                        self.bot.delete_message(self.group_id,
                                                self.message.message_id)

                        self.bot.send_message(BROADCAST_CHANNEL,
                                              "Group: @%s\n"
                                              "FORWARD "
                                              "MESSAGE"
                                              "\nUsername: %s\n%s" % (
                                                  self.group_username,
                                                  self.username,
                                                  self.message_text)
                                              )
                except Exception as exc:
                    print(exc)
                    traceback.print_exc()

            if _is_chat_forward:
                for _link in self.message.entities:
                    matches = re.search(REGEX_ALL,
                                        str(_link))
                    if matches is not None:
                        self.bot.delete_message(self.group_id,
                                                self.message.message_id)

                        self.bot.send_message(BROADCAST_CHANNEL,
                                              "Group: @%s\n"
                                              "TEXTLINK  "
                                              "MESSAGE: %s"
                                              "\nUsername: %s\n%s" % (
                                                  self.group_username,
                                                  matches.groups(),
                                                  self.username,
                                                  self.message_text)
                                              )
                        break

            if _is_new_users:
                self.set_new_users()


            elif _is_user_in_collection:
                _user_join_date = _db_user['JoinDate']
                _is_join_today = datetime.datetime.now() - \
                                 datetime.timedelta(days=1) \
                                 > _user_join_date

                if _is_forward and not _is_join_today:
                    #                           self.restrict_user()
                    self.bot.delete_message(self.group_id,
                                            self.message.message_id)

                    self.bot.send_message(BROADCAST_CHANNEL,
                                          "Group: @%s\n"
                                          "Forward MESSAGE: %s\n%s" % (
                                              self.group_username,
                                              self.username,
                                              self.message_text)
                                          )
                    self.spam_msgs_collection.update(
                        {
                            "_id": str(self.message_text.lower())
                        },
                        {
                            "$set":
                                {
                                    "_id":
                                        str(self.message_text.lower())
                                }
                        },
                        upsert=True
                    )
                elif _is_photo and not _is_join_today:
                    self.bot.delete_message(self.group_id,
                                            self.message.message_id)
                    self.bot.send_message(BROADCAST_CHANNEL,
                                          "Group: @%s\n"
                                          "INLINEKEYBOARD/IMAGE "
                                          "MESSAGE: %s\n%s" % (
                                              self.group_username,
                                              self.username,
                                              self.message_text)
                                          )
                elif _is_document and not _is_join_today:
                    self.bot.delete_message(self.group_id,
                                            self.message.message_id)
                    self.bot.send_message(BROADCAST_CHANNEL,
                                          "Group: @%s\n"
                                          "GIF/IMAGE MESSAGE: "
                                          "%s\n%s" % (
                                              self.group_username,
                                              self.username,
                                              self.message_text)
                                          )
                elif not _is_join_today:
                    self.check_message()
            elif not _is_user_admin:
                matches = re.search(REGEX_ALL, self.message_text)
                if matches is not None:
                    #                           self.restrict_user()
                    self.bot.delete_message(self.group_id,
                                            self.message.message_id)
                    # print("Check_message: %s" % matches.groups())
                    self.bot.send_message(BROADCAST_CHANNEL,
                                          "Group: @%s\n"
                                          "LONGTIME USER SPAM "
                                          "MESSAGE: %s"
                                          "\nUsername: %s\n%s" % (
                                              self.group_username,
                                              matches.groups(),
                                              self.username,
                                              self.message_text)
                                          )

    def get_admin_list(self):
        admins = self.bot.get_chat_administrators(self.message.chat.id)
        admin_list = ""
        for admin in admins:
            admin_list += str(admin.user.id) + " "
        print(str(admin_list))
        return admin_list


    def check_message(self):
        matches = re.search(REGEX, str(self.message_text).lower())
        if matches is not None:
            #           self.restrict_user()
            self.bot.delete_message(self.group_id,
                                    self.message.message_id)
            # print("Check_message: %s" % matches.groups())
            self.bot.send_message(BROADCAST_CHANNEL,
                                  "Channel: @%s\n"
                                  "SPAM MESSAGE: %s\nUsername: %s\n%s" % (
                                      self.group_username,
                                      matches.groups(),
                                      self.username,
                                      self.message_text)
                                  )
            self.spam_msgs_collection.update(
                {
                    "_id": str(self.message_text.lower())
                },
                {
                    "$set":
                        {
                            "_id": str(self.message_text.lower())
                        }
                },
                upsert=True
            )

    def _is_msg_spam(self):
        matches = re.search(REGEX, self.message_text)
        if matches is not None:
            return True

        matches = re.search(REGEX_ALL, self.message_text)
        if matches is not None:
            return True
        return False

    """
        Method to add users into the whitelist
    """

    def add_user_to_whitelist(self, username):
        self.users_whitelist.insert(
            {
                "key": username
            })
        self.bot.send_message(
            BROADCAST_CHANNEL,
            "User <b>%s</b> was successfully added into the whitelist!" % username,
            parse_mode='HTML'
        )
        self.bot.send_message(
            self.user_id,
            "User <b>%s</b> was successfully added into the whitelist!" % username,
            parse_mode='HTML'
        )

    """
        Restrict chat member for 7 days
    """

    def restrict_user(self):
        self.bot.restrict_chat_member(
            self.group_id,
            self.user_id,
            until_date=datetime.datetime.now() + datetime.timedelta(days=7),
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )

    """
        Method checks is user new and add him to db collection
    """

    def set_new_users(self):
        # loop uses to check each user, on the way if any user invite somebody.
        for user in self.new_users:
            try:
                # Is spam in the nickname
                matches = re.search(REGEX, str(user.first_name))
                if matches is not None:
                    self.restrict_user()

                # Update data of user
                self.col_users.insert(
                    {
                        "_id": user.id
                    },
                    {
                        "$set":
                            {
                                "_id": user.id,
                                "first_name": user.first_name,
                                "username": user.username,
                                "Balance": 0,
                                "IsVerified": False,
                                "JoinDate": datetime.datetime.now()
                            }
                    }, upsert=True
                )

                # Send msg about new user to the monitor channel
                self.bot.send_message(BROADCAST_CHANNEL,
                                      "Channel: @%s    Title: %s\n"
                                      "New User: %s\n%s" % (
                                          self.group_username,
                                          self.message.chat.title,
                                          user.first_name,
                                          user.username)
                                      )
            except Exception as exc:
                print(exc)

            # send captcha
            if self.col_users.find_one({"_id": self.user_id})['IsVerified'] is False:
                # Send captcha to the new users that joined into the group if they weren't verified.
                self.send_captcha(self.new_users[0].first_name,
                                  self.new_users[0].id)
        self.bot.delete_message(self.group_id, self.message.message_id)

    """
        Send captcha to check, Is user bot?
    """

    def send_captcha(self, first_name, user_id):
        msg = self.bot.send_message(
            self.group_id,
            "Welcome [%s](tg://user?id=%s) to Volentix Group. Confirm that you're not a bot" % (
                first_name,
                user_id),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="I'm not a bot",
                            url="https://t.me/vtxprotector_bot"
                        )
                    ]
                ])
        )
        self.col_captcha.update(
            {
                "_id": msg.message_id
            },
            {
                "$set": {
                    "_id": msg.message_id,
                    "group_id": self.group_id,
                    "Datetime": datetime.datetime.now()
                }
            }, upsert=True
        )


    def captcha_processing(self):
        captcha_list = list(self.col_captcha.find())

        for _c in captcha_list:
            try:
                if datetime.datetime.now() > _c['Datetime'] + datetime.timedelta(seconds=10):
                    self.bot.delete_message(chat_id=_c['group_id'],
                                            message_id=_c['_id'])
                    self.col_captcha.remove(_c)
            except Exception as exc:
                self.col_captcha.remove(_c)
                traceback.print_exc()
                print(exc)

        messages = list(self.pending_msgs_collection.find())

        for _msg in messages:
            try:
                if datetime.datetime.now() > _msg['Datetime'] + datetime.timedelta(minutes=5):
                    self.bot.delete_message(
                        MY_ID,
                        _msg['_id']
                    )
                    self.pending_msgs_collection.remove(_msg)
            except Exception as exc:
                self.pending_msgs_collection.remove(_msg)
                print(exc)

    """
        Get group username
    """

    def get_group_username(self):
        try:
            return str(self.message.chat.username)
        except:
            return str(self.message.chat.id)

    """
            Get User username
    """

    def get_user_username(self):
        try:
            return str(self.message.from_user.username)
        except:
            return None

    def wait_new_message(self):
        while True:
            updates = self.bot.get_updates()
            if len(updates) > 0:
                break
        update = updates[0]
        self.bot.get_updates(offset=update["update_id"] + 1)
        return update

    @staticmethod
    def get_action(message):
        _is_document = False

        if message['message'] is not None:
            menu_option = message['message']['text']
            _is_document = message['message']['document'] is not None
        elif message["callback_query"] != 0:
            menu_option = message["callback_query"]["data"]

        return str(menu_option), _is_document


    """
        Check each user actions
    """
    def action_processing(self):

        if "/faq" in self.text:
            self.get_questions()

        elif "get_questions|" in self.text:
            self.get_questions()

        elif "answer|" in self.text:
            self.get_answer()

        elif "vote|" in self.text:
            self.check_vote()

        elif "/balance" in self.text:
            if 'private' in self.message.chat.type:
                self.print_balance()
            else:
                self.bot.delete_message(
                    self.group_id,
                    self.message.message_id
                )



        elif "/add" in self.message_text:
            username = self.message_text.split(' ')[1].replace('@', '')
            self.add_user_to_whitelist(username)

        elif "/start" in self.message_text:
            if not self._is_verified:
                self.bot.send_message(
                    self.user_id,
                    WELCOME_MESSAGE,
                    parse_mode='html',
                    disable_web_page_preview=True
                )
                self.bot.send_message(
                    self.user_id,
                    "<b>⚠️SCAMMER 🚨\n" 
                    "BEWARE OF ANYONE SENDING YOU PM WHO IS NOT ADMIN STATUS AND PRETENDING TO ASSIST YOU IN GETTING VTX.\n"
                    "NEVER SEND FUNDS TO ANY BTC or ETH address or any address sent to you via PM. Volentix WILL NEVER DO THAT!</b>\n<b>The Volentix group Admins are</b>:\n@Vaudevillian\n@T_Naqi\n@ioannafo\n@Vionidas\n@lou1ou\n@Realrhys\n@TheVguy\n@buona4tuna\n@Jelly_SL\n@sylvaincormier",
                    parse_mode='html',
                    disable_web_page_preview=True
                )
                self.col_users.update(
                    {
                        "_id": self.user_id
                    },
                    {
                        "$set":
                            {
                                "IsVerified": True
                            }
                    }
                )

                
            else:
                self.col_users.update(
                    {
                        "_id": self.user_id
                    },
                    {
                        "$set":
                            {
                                "_id": self.user_id,
                                "first_name": self.first_name,
                                "username": self.username,
                                "IsVerified": True,
                                "JoinDate": datetime.datetime.now() - datetime.timedelta(
                                    days=5)
                            }
                    }, upsert=True
                )
                self.bot.send_message(
                    self.user_id,
                    WELCOME_MESSAGE,
                    parse_mode='html'
                )
                self.bot.send_message(
                    self.user_id,
                    "<b>⚠️SCAMMER 🚨\n"
                    "BEWARE OF ANYONE SENDING YOU PM WHO IS NOT ADMIN STATUS AND PRETENDING TO ASSIST YOU IN GETTING VTX.\n"
                    "NEVER SEND FUNDS TO ANY BTC or ETH address or any address sent to you via PM. Volentix WILL NEVER DO THAT!</b>\n<b>The Volentix group Admins are</b>:\n@Vaudevillian\n@T_Naqi\n@ioannafo\n@Vionidas\n@lou1ou\n@Realrhys\n@TheVguy\n@buona4tuna\n@Jelly_SL\n@sylvaincormier",
                    parse_mode='html',
                    disable_web_page_preview=True
                )


        elif "|confirm" in self.message_text:
            user_id = self.message_text.split('|')[0]
            print(user_id)
            print(type(user_id))
            user = self.col_users.find_one({"_id": int(user_id)})
            _is_verified = user['IsVerified']
            if not _is_verified:
                self.col_users.update(
                    {
                        "_id": int(user_id)
                    },
                    {
                        "$set":
                            {
                                "IsVerified": True
                            }
                    }
                )
                self.bot.send_message(
                    BROADCAST_CHANNEL,
                    "Channel: @%s    Title: %s\n"
                    "User Confirmed: %s\n%s" % (
                        self.message.chat.username,
                        self.message.chat.title,
                        user['first_name'],
                        str(user['username']))
                )

    def check_vote(self):
        try:
            split = self.text.split('|')
            _id = split[1]
            answer_id = int(split[2])

            q = self.col_questions.find_one({"_id": ObjectId(_id)})
            if str(self.user_id) in str(q):
                self.bot.answer_callback_query(
                    self.new_message.callback_query.id,
                    text="❗️You have already voted and can't change vote❗️",
                    show_alert=True
                )
                return

            _is_users_auth = self.col_users.find_one({'_id': self.user_id, "IsVerified": True}) is not None
            if not _is_users_auth:
                self.bot.answer_callback_query(
                    self.new_message.callback_query.id,
                    text="❗️You need to complete authetication in the %s. Push start btn❗️" % quiz_bot,
                    show_alert=True
                )
                return

            if q['Completed'] is False:

                _is_winner_exists = q['Winner'] is not None


                repliers = q[q['answers'][answer_id]]
                repliers.append([self.user_id, self.first_name, datetime.datetime.now().timestamp()])
                self.col_questions.update(
                    {"_id": ObjectId(_id)},
                    {
                        "$set": {
                            q['answers'][answer_id]: repliers
                        }
                    }
                )

                if answer_id == q['correct_answer'] and not _is_winner_exists:
                    self.col_questions.update(
                        {
                            "_id": ObjectId(_id)
                        },
                        {
                            "$set": {
                                "Winner": [self.user_id, self.first_name]
                            }
                        }
                    )
                    user = self.col_users.find_one({"_id": self.user_id})
                    self.col_users.update(
                        user,
                        {
                            "$set":
                                {
                                    "Balance": float(user['Balance']) + win_amount
                                }
                        }, upsert=True
                    )

                    self.bot.answer_callback_query(
                        self.new_message.callback_query.id,
                        text="🔥Congratulations! You Won and received 10 VTX for %s️⃣" % (int(answer_id) + 1),
                        show_alert=True
                    )
                else:
                    self.bot.answer_callback_query(
                        self.new_message.callback_query.id,
                        text="✅You voted for %s️⃣" % (int(answer_id) + 1),
                        show_alert=True
                    )
            else:
                self.bot.answer_callback_query(
                    self.new_message.callback_query.id,
                    text="❗️Attention: Quiz completed❗️",
                    show_alert=True
                )
        except Exception as exc:
            print(exc)

    def print_balance(self):
        user = self.col_users.find_one({"_id": self.user_id})
        self.bot.send_message(
            self.user_id,
            '<b>Balance</b>: %s VTX' % user['Balance'],
            parse_mode='HTML'
        )


    def get_questions(self):
        try:
            if "get_questions|" in self.text:
                step = int(self.text.split('|')[1])
            else:
                step = 5

            if step < len(faq_data):
                reply_markup = [[]]
                for x in range(step - 5, step):
                    reply_markup.append(
                        [
                            InlineKeyboardButton(
                                text="%s" % faq_data[x]['Q'],
                                callback_data='answer|%s' %
                                              str(faq_data[x]['id']))
                        ]
                    )
                reply_markup.append(
                    [
                        InlineKeyboardButton(
                            text="Previous",
                            callback_data='get_questions|%s' % str(
                                step - 5)),
                        InlineKeyboardButton(
                            text="Next",
                            callback_data='get_questions|%s' % str(
                                step + 5))
                    ]
                )
                try:
                    self.bot.delete_message(self.group_id,
                                            self.message.message_id)
                except Exception as exc:
                    print(exc)

                self.bot.send_message(
                    self.group_id,
                    '<b>Frequently Asked Questions</b>',
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(reply_markup)
                )
        except Exception as exc:
            print(exc)
            traceback.print_exc()

    def get_answer(self):
        try:
            self.bot.delete_message(self.group_id,
                                    self.message.message_id)
        except Exception as exc:
            print(exc)
        _id = str(self.text.split('|')[1])
        item = self.get_data_item(_id)
        self.bot.send_message(
            self.group_id,
            '<b>%s</b>\n%s' % (item['Q'], item['A']),
            parse_mode='HTML'
        )

    @staticmethod
    def get_data_item(_id):

        for x in faq_data:
            if x['id'] == _id:
                return x


def main():
    while True:
        try:
            Defender()
        except Exception as e:
            if "Timed out" not in str(e):
                traceback.print_exc()
                print(e)


if __name__ == '__main__':
    main()
