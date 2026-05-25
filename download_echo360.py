from bs4 import BeautifulSoup as bs
from bs4 import Tag
from pathlib import Path
from time import sleep
from typing import cast
import datetime as dt
import json
import pandas as pd
import requests
import yt_dlp.extractor.common
import yt_dlp.networking.impersonate

from utils import dump_for_debugging, logTime, load_cookies, sanitise_filename

# Config
HOMEPAGE = input(
"""
Copy the homepage URL of the subject you want to download lectures from and \
paste it here, then press Enter:
"""
)
# START = 28 # Set this to the number of the the most recent lecture that you already have or 0
start_number = input("Enter the number of the most recent lecture that you already have or 0: ")
YEAR = 2026
MONTH = 3
LECTURE_STREAMS = False
# Add the day of month and hour of day for the first week of lessons in your stream
LESSONS_ATTENDED = [
    dt.datetime(YEAR, MONTH, 2, 13),
    dt.datetime(YEAR, MONTH, 3, 14),
    dt.datetime(YEAR, MONTH, 5, 12)
]
LESSONS_CANCELLED = [
    dt.datetime(YEAR, 4, 16)
]

FORMAT_SORT = "+width~640"
FORMAT_SELECT = "bv+q0-Default"

COOKIE = "cookies_echo360.txt"
cookie_dict = load_cookies(COOKIE)
del cookie_dict['CloudFront-Key-Pair-Id']
del cookie_dict['CloudFront-Policy']
del cookie_dict['CloudFront-Signature']
del cookie_dict['CloudFront-Tracking2']

LESSONTIME_FMTSPEC = "%a %I %p"
LESSONDATE_FMTSPEC = "%Y-%m-%d"

DEBUG_MODE = True

print('Start: ' + logTime() + '\n')
START = int(start_number)

def getTime(s: str) -> dt.datetime:
    s = s.removesuffix('Z')
    return dt.datetime.strptime(s[:-4], "%Y-%m-%dT%H:%M:%S")

def get_lesson_url(lesson) -> str:
    return f"https://echo360.net.au/lesson/{lesson['lesson']['id']}/classroom"

jsonDecoder = json.JSONDecoder()
def get_json_decoded(refURL: str) -> dict:
    resp = requests.get(url=refURL, cookies=cookie_dict)
    soup = bs(resp.text, "html.parser")
    html_str = soup.body.find_all_next(name="script") # type: ignore
    html_str = html_str[1].string
    html_str = cast(str, html_str)
    a = html_str.find('echoPlayerV2FullApp"]("')
    b = html_str.rfind("echoPlayerV2FullApp")
    html_str = html_str[a:b]
    html_str = html_str[:html_str.rfind('");')]
    html_str = html_str.removeprefix('echoPlayerV2FullApp"]("')
    html_str = html_str.strip().replace(r'\"', '"')
    decoded_json = jsonDecoder.decode(html_str)
    if DEBUG_MODE:
        refURL_sanitised = sanitise_filename(refURL)
        dump_for_debugging({
            f"{refURL_sanitised}_request_decoded.json": decoded_json,
            f"{refURL_sanitised}_request_headers.json": dict(resp.headers),
            f"{refURL_sanitised}_request.html": soup.prettify(),
        })
    return decoded_json

def get_videoURL(lesson_data: dict) -> str:
    medias = lesson_data["video"]["playableMedias"]
    videoURL = ''
    dim = {}
    for m in medias:
        if (
            ("Video" in m["trackType"])
            and
            ("Audio" in m["trackType"])
            and
            (m["sourceIndex"] == 1)
            ):
            if "dimensions" in m.keys():
                dim.update({m["dimensions"]["width"]: m["uri"]})
            else:
                dim.update({m["sourceIndex"]: m["uri"]})
    k = list(dim.keys())
    if len(k) > 1:
        k.sort()
    videoURL = dim[k[0]]
    assert(videoURL != '')
    return videoURL.removesuffix('&x-act=videoView&x-src=desktop')

def get_date_from_time_attr(d: Tag, s: str) -> dt.datetime:
    date = cast(Tag, d.find(itemprop=s))
    date = str(date.get('content'))
    return dt.datetime.strptime(date, "%d-%m-%Y")

date_store = Path(f"dates{YEAR}.txt")
date_store.touch()
with open(date_store, 'rt') as f:
    hols_as_strings = f.readlines()

def download_key_dates(fatal: bool = False) -> bs | bool:
    UnimelbIE = yt_dlp.extractor.common.InfoExtractor(downloader=yt_dlp.YoutubeDL())
    webpage = UnimelbIE._download_webpage_handle(
        url_or_request="https://www.unimelb.edu.au/dates", video_id='',
        note="Downloading Unimelb key dates", impersonate=True, fatal=fatal
    )
    if DEBUG_MODE:
        if isinstance(webpage, tuple):
            dump_for_debugging({
                "dates.html": webpage[0],
                "dates_response.txt": webpage[1].headers.as_string()
            })
    if webpage:
        return bs(webpage[0], "html.parser")
    else:
        return webpage

if (
    (len(hols_as_strings) == 0)
    or
    (DEBUG_MODE)
):
    soup = download_key_dates(fatal=False)
    if not soup:
        print("Unable to download key dates, retrying in 10 seconds")
        sleep(10)
        soup = download_key_dates(fatal=True)
    if not soup:
        print("Failed to download key dates")
        exit()

    soup = cast(bs, soup)
    htmlstr = soup.find(class_="mobile-wrap"
        ).table.tbody.find_all( # pyright: ignore[reportOptionalMemberAccess]
            name='tr', itemscope=True
        )

    holidays = []
    for tr in htmlstr:
        activity = tr.select_one('td[headers*="wcag-activity"]'
        ).find( # pyright: ignore[reportOptionalMemberAccess]
            itemprop="name"
        ).getText( # pyright: ignore[reportOptionalMemberAccess]
        ).lower()
        date = cast(Tag, tr.select_one('td[headers*="wcag-date"]'))
        startDate = get_date_from_time_attr(date, "startTime")
        endDate = get_date_from_time_attr(date, "endTime")
        if (
            (len(tr['class']))
            and
            (tr['class'][0] == 'holiday')
            and
            (startDate == endDate)
            ):
            holidays.append(startDate.date())
        elif (
            (activity.find("easter holiday") >= 0)
            or
            (activity.find("non-teaching period") >= 0)
            or
            (activity.find("christmas holiday") >= 0)
            ):
            daterange = pd.date_range(start=startDate, end=endDate).to_pydatetime().tolist()
            for day in daterange:
                holidays.append(day.date())

    hols_as_strings = [dt.datetime.strftime(h, LESSONDATE_FMTSPEC) + '\n' for h in holidays]
    hols_as_strings.sort()
    hols_as_strings = set(hols_as_strings)
    with open(date_store, 'wt') as f:
        f.writelines(hols_as_strings)
else:
    holidays = set([
        dt.datetime.strptime(l.strip(), LESSONDATE_FMTSPEC).date()
        for l in hols_as_strings
    ])

def is_lesson_in_attended_stream() -> bool:
    for lesson_in_stream in LESSONS_ATTENDED:
        if (
            (t.weekday() == lesson_in_stream.weekday())
            and
            (t.hour == lesson_in_stream.hour)
            ):
            return True
    return False

lessons_cancelled = set([t.date() for t in LESSONS_CANCELLED])
syllabus_dict = {}
r = requests.get(url=f"{HOMEPAGE.removesuffix("home")}syllabus", cookies=cookie_dict)
syllabus = r.json()['data']
if DEBUG_MODE:
    dump_for_debugging({
        f"syllabus_response_{r.status_code}.txt": dict(r.headers),
        f"syllabus.json": r.json(),
    })

for l in syllabus:
    lesson_attended = False
    lesson_data = l['lesson']
    if 'timing' in lesson_data['lesson'].keys():
        t = getTime(lesson_data['lesson']['timing']['start'])
    else:
        t = getTime(lesson_data['lesson']['createdAt'])

    if (
        (t.date() in holidays)
        or
        (t.date() in lessons_cancelled)
        ):
        lesson_attended = False
    elif LECTURE_STREAMS:
        lesson_attended = is_lesson_in_attended_stream()
    else:
        lesson_attended = True

    if lesson_attended:
        syllabus_dict.update({t: lesson_data})

syllabus_as_list = list(syllabus_dict.items())[START:]
startTime, lesson = syllabus_as_list.pop(0)
refURL = get_lesson_url(lesson)
lesson_json = get_json_decoded(refURL)
COURSE_CODE = lesson_json['sectionInfo']['course']['courseIdentifier']

video_download_opts = {
    'cookiefile': COOKIE,
    'format_sort': [FORMAT_SORT],
    'format': FORMAT_SELECT,
    'paths': {'home': f"download/{COURSE_CODE}/Lectures"},
    'impersonate': yt_dlp.networking.impersonate.ImpersonateTarget(),
}
echo360DL = yt_dlp.YoutubeDL(video_download_opts) # type: ignore

def download(st: dt.datetime, idx: int, url:str) -> None:
    filename = f'{COURSE_CODE} L{idx:02} {st.strftime("%a %d %b")}'
    if LECTURE_STREAMS:
        filename += ' ' + st.strftime("%I %p")
    filename += ".mp4"
    print(f"[{logTime()}]\tDownloading {url} to '{filename}'")
    echo360DL.params['outtmpl']['default'] = filename # type: ignore
    echo360DL.params['verbose'] = DEBUG_MODE
    echo360DL.download([url])
    return None

videoURL = get_videoURL(lesson_json)
counter = START + 1
download(st=startTime, idx=counter, url=videoURL)

for startTime, lesson in syllabus_as_list:
    counter += 1
    if len(lesson["medias"]) == 0: continue
    refURL = get_lesson_url(lesson)
    videoURL = get_videoURL(get_json_decoded(refURL))
    download(st=startTime, idx=counter, url=videoURL)

print('\nFinish: ' + logTime())
