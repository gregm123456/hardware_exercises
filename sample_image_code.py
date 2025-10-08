import config
from update_status import update_status
import json
import telegram
import os
import base64
import urllib.request
from datetime import datetime
import time


TELEGRAM_FRIEND_UID = config.TELEGRAM_FRIEND_UID
MESSAGEBOX_PATH = config.MESSAGEBOX_PATH
user_path = f'{MESSAGEBOX_PATH}/{TELEGRAM_FRIEND_UID}'
TELEGRAM_TOKEN = config.TELEGRAM_TOKEN
SD_IMAGE_WEBUI_SERVER_URL = config.SD_IMAGE_WEBUI_SERVER_URL
PICTURE_COMING_MESSAGE = config.PICTURE_COMING_MESSAGE
IMAGE_PROMPT_PREFIX = config.IMAGE_PROMPT_PREFIX
IMAGE_PROMPT_SUFFIX = config.IMAGE_PROMPT_SUFFIX
NEGATIVE_IMAGE_PROMPT = config.NEGATIVE_IMAGE_PROMPT
SLEEP = config.SLEEP

# set image_directory to {user_path}/images, creating the directory if it does not exist
image_directory = f'{user_path}/images'
os.makedirs(image_directory, exist_ok=True)

bot = telegram.Bot(token=TELEGRAM_TOKEN)


def generate_base64_image(image_prompt):
    print("Calling txt2img API...")
    payload = {
        "prompt": image_prompt,
        "negative_prompt": NEGATIVE_IMAGE_PROMPT,
        "seed": -1,
#        "steps": 14,
        "steps": 7,
        "width": 512,
        "height": 576,
#        "cfg_scale": 6.0,
        "cfg_scale": 1.5,
        "sampler_name": "DPM++ 2M Karras",
        "n_iter": 1,
        "batch_size": 1
    }
    image_path = call_txt2img_api(**payload)
    return image_path


def call_txt2img_api(**payload):
    print("Calling txt2img API...")
    response = call_api('sdapi/v1/txt2img', **payload)
    for index, image in enumerate(response.get('images')):
        save_path = os.path.join(image_directory, f'txt2img-{timestamp()}-{index}.png')
        decode_and_save_base64(image, save_path)
    last_image_path = os.path.join(image_directory, f'txt2img-{timestamp()}-{len(response.get("images"))-1}.png')
    return last_image_path


def timestamp():
    print("Getting timestamp...")
    return datetime.fromtimestamp(time.time()).strftime("%Y%m%d-%H%M%S")


def call_api(api_endpoint, **payload):
    print(f"Calling API endpoint: {api_endpoint}")
    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        f'{SD_IMAGE_WEBUI_SERVER_URL}/{api_endpoint}',
        headers={'Content-Type': 'application/json'},
        data=data,
    )
    response = urllib.request.urlopen(request)
    return json.loads(response.read().decode('utf-8'))


def decode_and_save_base64(base64_str, save_path):
    print(f"Decoding and saving base64 image to {save_path}")
    with open(save_path, "wb") as file:
        file.write(base64.b64decode(base64_str))


def send_picture_coming_message():
    print("Sending picture coming message...")
    bot.send_message(chat_id=TELEGRAM_FRIEND_UID, text=PICTURE_COMING_MESSAGE)
    # update the "content" of the last "assistant" message in conversation.json by appending "PICTURE_COMING_MESSAGE" to the existing content value and saving the file with this updated content value
    with open(f"{user_path}/conversation.json", "r") as file:
        conversation_data = json.load(file)
        last_assistant_message = next((message for message in reversed(conversation_data) if message["role"] == "assistant"), None)
        if last_assistant_message:
            last_assistant_message["content"] += f" {PICTURE_COMING_MESSAGE}"
            with open(f"{user_path}/conversation.json", "w") as file:
                json.dump(conversation_data, file, indent=4)
                file.flush()


def get_last_bot_message():
    print("Getting last bot message...")
    with open(f"{user_path}/conversation.json", "r") as file:
        conversation_data = json.load(file)
        assistant_messages = [message["content"] for message in conversation_data if message["role"] == "assistant"]
        last_message = assistant_messages[-1] if len(assistant_messages) > 0 else ""
        return last_message


def rename_and_archive_interrupted_image(image_path):
    print("Renaming and archiving interrupted image...")
    interrupted_image_path = os.path.join(image_directory, f'interrupted_{image_path.split("/")[-1]}')
    os.rename(image_path, interrupted_image_path)
    os.makedirs(f'{user_path}/archive', exist_ok=True)
    os.rename(interrupted_image_path, f'{user_path}/archive/{interrupted_image_path.split("/")[-1]}')


def archive_successful_image(image_path):
    print("Archiving successful image...")
    os.makedirs(f'{user_path}/archive', exist_ok=True)
    os.rename(image_path, f'{user_path}/archive/{image_path.split("/")[-1]}')


def send_image():
    print("Sending image...")
    # read converation.json, extract the last assistant message and append it to the base image prompt
    last_message = get_last_bot_message()
    # remove all occurences of the colon character from the last_message
    last_message = last_message.replace(":", "")
    image_prompt = IMAGE_PROMPT_PREFIX + last_message + IMAGE_PROMPT_SUFFIX
    # If we get the image path, then send PICTURE_COMING_MESSAGE, append it to last statememt in conversation.json and send the image
    update_status("originating", "watching")
    try:
        print("Generating image...")
        image_path = generate_base64_image(image_prompt)
        # update_status("originating", "originated")
        print("Image generated")
        number_of_messages = len([name for name in os.listdir(user_path) if name.startswith('message_')])
        print(f"Number of messages: {number_of_messages}")
        if number_of_messages == 0:
            print("Sending picture coming message...")
            if PICTURE_COMING_MESSAGE:
                send_picture_coming_message()
            print("Sending image...")
            bot.send_photo(chat_id=TELEGRAM_FRIEND_UID, photo=open(image_path, 'rb'))
            print("Image sent")
            archive_successful_image(image_path)
            print("Image archived")
            time.sleep(SLEEP)
            print("Slept.")
        else:
            rename_and_archive_interrupted_image(image_path)
        # update_status("originated", "watching")
    except Exception as e:
        print(f"An image generation time error occurred: {str(e)}")
        # update_status("originating", "watching")
    return

