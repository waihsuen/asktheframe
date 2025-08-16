import sys
import os
import textwrap
from dotenv import load_dotenv
from types import SimpleNamespace

# Load environment variables
load_dotenv()

# Setting up directories
picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pic")
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "lib")
if os.path.exists(libdir):
    sys.path.append(libdir)

import requests
import json
from datetime import datetime

# from waveshare_epd import epd7in5_V2
import time
from PIL import Image, ImageDraw, ImageFont
import traceback
import logging

API_URL = int(os.getenv("API_URL", ""))

logging.basicConfig(level=logging.DEBUG)


def get_bus_arrival(api_key, bus_stop_code):
    url = f"{API_URL}/busarrival?BusStopCode={bus_stop_code}"
    headers = {"AccountKey": api_key, "accept": "application/json"}

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        services = data.get("Services", [])
        bus_info = []

        for service in services:
            service_no = service["ServiceNo"]
            arrival_times = []
            for bus in ["NextBus", "NextBus2", "NextBus3"]:
                if service.get(bus):
                    eta = service[bus]["EstimatedArrival"]
                    if eta:
                        eta_time = datetime.strptime(eta, "%Y-%m-%dT%H:%M:%S%z")
                        time_diff = (eta_time - datetime.now(eta_time.tzinfo)).total_seconds() / 60
                        arrival_times.append(round(time_diff))
            if arrival_times:
                bus_info.append((service_no, arrival_times))
        return bus_info
    else:
        logging.error("Error: Unable to fetch data. Status code: " + str(response.status_code))
        return []


def display_bus_arrivals_simulated(epd, draw, bus_info, Himage):
    draw.rectangle((0, 0, epd.width, epd.height), fill=255)  # Clear the display

    if bus_info:
        title_font = ImageFont.truetype(os.path.join(libdir, "OpenSans-Bold.ttf"), 32)
        title = f"Service: {bus_info[0][0]}"
        title_bbox = draw.textbbox((0, 0), title, font=title_font)

        draw.rectangle((0, 0, 800, 100), fill=0)
        draw.text(((800 - title_bbox[2]) / 2, 20), title, font=title_font, fill=255)

    else:
        logging.info("Error, no data")
        return

    if bus_info[0][1]:
        first_arrival = bus_info[0][1][0]
        first_text = "Arriving" if first_arrival < 1 else f"{first_arrival}"
        first_font_size = 86 if first_arrival < 1 else 140
        first_font = ImageFont.truetype(os.path.join(libdir, "OpenSans-Bold.ttf"), first_font_size)
        first_bbox = draw.textbbox((0, 0), first_text, font=first_font)
        draw.text(((800 - first_bbox[2]) / 2, 160), first_text, font=first_font, fill=0)

        # Extract arrival times from the list (excluding the first arrival time)
        # second_arrival = bus_info[0][1][1]
        # third_arrival = bus_info[0][1][2]
        arrival_times = bus_info[0][1][1:]

        # Join the arrival times with " | "
        next_text = " | ".join(map(str, arrival_times))
        next_font = ImageFont.truetype(os.path.join(libdir, "OpenSans-Bold.ttf"), 86)
        first_bbox = draw.textbbox((0, 0), next_text, font=next_font)
        draw.text(((800 - first_bbox[2]) / 2, 360), next_text, font=next_font, fill=0)

    else:
        logging.info("Error, no data")
        return

    # Display for Bus Stop A (left column)
    # for service_no, arrival_times in bus_info_A:
    #     draw.rectangle((box_start_x, box_start_y, box_end_x, box_end_y), fill=0)
    #     draw.text((bus_num_x, bus_num_y), service_no, font=font, fill=255)

    #     times_text = " | ".join(map(str, arrival_times))
    #     draw.text((bus_timing_x, bus_timing_y), times_text, font=font, fill=0)
    #     start_y += padding_y

    # Save the generated image to a file for review
    Himage.save("bus_arrivals_simulated.png")
    print("Simulated display saved as 'bus_arrivals_simulated.png'")


# 800 x 480
epd = SimpleNamespace(width=800, height=480)
api_key = os.getenv("API_KEY")
bus_stop_code_A = os.getenv("BUS_STOP_CODE_A")
bus_info_A = get_bus_arrival(api_key, bus_stop_code_A)
# print(bus_info_A)
Himage = Image.new("1", (epd.width, epd.height), 255)
draw = ImageDraw.Draw(Himage)

display_bus_arrivals_simulated(epd, draw, bus_info_A, Himage)
