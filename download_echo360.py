from base64 import b64decode
from bs4 import BeautifulSoup as bs
from pathlib import Path
from subprocess import run
import datetime as dt
import json
import pandas as pd

from utils import logTime

# Config
HOMEPAGE = input(
"""
Copy the homepage URL of the subject you want to download lectures from and \
paste it here, then press Enter:
"""
)
START = 19 # Set this to the number of the the most recent lecture that you already have or 0
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

SUPPRESS_WARNINGS = True

COOKIE = "cookies_echo360.txt"

COOKIEPATH = Path(COOKIE).absolute()
COOKIEPATH.touch()
with open(COOKIEPATH, 'rt') as f:
    c = f.read()

if len(c) <= 1:
    print(f"\nPlease export cookies from your browser with Cookie-Editor, then paste into '{COOKIEPATH}'")
    input("Press Enter to continue...")

COOKIE_OPTION = f'--cookies "{COOKIEPATH}"'
OPTIONS_CONSTANT = ' '.join([
    '--no-warnings' if SUPPRESS_WARNINGS else '',
    COOKIE_OPTION,
    '--embed-metadata',
    '-S +width~640',
    '-f "bv+q0-Default"',
    '-P "download/{course_code}/Lectures"',
    # '-F',
])

YTDLP_CMD = "yt-dlp.exe"
LESSONTIME_FMTSPEC = "%a %I %p"
LESSONDATE_FMTSPEC = "%Y-%m-%d"
lessons_cancelled = set([t.date() for t in LESSONS_CANCELLED])

OPTIONS_DUMP_JSON = ' '.join([
    f'"{YTDLP_CMD}"',
    '--no-warnings',
    '--skip-download',
    '--dump-pages'
])

jsonDecoder = json.JSONDecoder()

run(' '.join([
    '"{}"',
    '--no-warnings' if SUPPRESS_WARNINGS else '\0',
    '--force-overwrite',
    COOKIE_OPTION,
    '--referer "{}"',
    '-o syllabus.json',
    '--dump-pages',
    '"{}syllabus"'
]).format(YTDLP_CMD, HOMEPAGE, HOMEPAGE.removesuffix("home")))

with open("syllabus.json", 'rt') as j:
    syllabus = json.load(j)['data']

def getTime(s: str) -> dt.datetime:
    s = s.removesuffix('Z')
    return dt.datetime.strptime(s[:-4], "%Y-%m-%dT%H:%M:%S")

def get_params(lesson) -> tuple[str, str]:
    mediaTitle = lesson['lesson']['name']
    refURL = f'https://echo360.net.au/lesson/{lesson['lesson']['id']}/classroom'
    return mediaTitle, refURL

def dump_soup(opts: str, url: str) -> bs:
    return bs(
        b64decode(
            run(' '.join([
                    OPTIONS_DUMP_JSON,
                    opts,
                    f'"{url}"'
                ]), capture_output=True, text=True
            ).stdout.format().splitlines()[3].strip(), validate=True
        ).decode(), "html.parser"
    )

def get_json_decoded(refURL: str) -> dict:
    html_str = dump_soup(
        opts=COOKIE_OPTION + f' --referer "{refURL}"',
        url=refURL
    ).find_all(
        name="script"
    )[-1].getText()
    a = html_str.find("echoPlayerV2FullApp")
    b = html_str.rfind("echoPlayerV2FullApp")
    html_str = html_str[a:b]
    html_str = html_str[:html_str.rfind('");')]
    html_str = html_str.removeprefix('echoPlayerV2FullApp"]("')
    html_str = html_str.strip().replace(r'\"', '"')
    return jsonDecoder.decode(html_str)

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

def get_date_from_time_attr(d: str, s: str) -> dt.datetime:
    return dt.datetime.strptime(
        d.find(
            itemprop=s # type: ignore
        )['content'], "%d-%m-%Y"
    )

date_store = Path(f"dates{YEAR}.txt")
date_store.touch()
with open(date_store, 'rt') as f:
    hols_as_strings = f.readlines()

if len(hols_as_strings) == 0:
    htmlstr = dump_soup(
        opts='--extractor-args "generic:impersonate"',
        url="https://www.unimelb.edu.au/dates"
    ).find(
        class_="mobile-wrap"
    ).table.tbody.find_all( # pyright: ignore[reportOptionalMemberAccess]
        name='tr', itemscope=True
    )

    holidays = []
    for tr in htmlstr:
        activity = tr.select_one(
            'td[headers*="wcag-activity"]'
        ).find( # type: ignore
            itemprop="name"
        ).getText().lower() # type: ignore
        date = tr.select_one('td[headers*="wcag-date"]')
        startDate = get_date_from_time_attr(date, "startTime") # type: ignore
        endDate = get_date_from_time_attr(date, "endTime") # type: ignore
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

    hols_as_strings = set([
        dt.datetime.strftime(
            h, LESSONDATE_FMTSPEC
        ) + '\n'
        for h in holidays
    ])
    with open(date_store, 'wt') as f:
        f.writelines(hols_as_strings)
else:
    holidays = set([
        dt.datetime.strptime(
            l.strip(), LESSONDATE_FMTSPEC
        ).date()
        for l in hols_as_strings
    ])

def is_lesson_in_attended_stream(lesson_attended: bool) -> bool:
    for lesson_in_stream in LESSONS_ATTENDED:
        if (
            (t.weekday() == lesson_in_stream.weekday())
            and
            (t.hour == lesson_in_stream.hour)
            ):
            return True
    return lesson_attended

syllabus_dict = {}
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
        lesson_attended = is_lesson_in_attended_stream(lesson_attended)
    else:
        lesson_attended = True

    if lesson_attended:
        syllabus_dict.update({t: lesson_data})

def download(st: dt.datetime, idx: int, opts: str, title: str, ref: str, url:str) -> None:
    filename = f'{COURSE_CODE} L{idx:02} {st.strftime("%a %d %b")}'
    if LECTURE_STREAMS:
        filename += ' ' + st.strftime("%I %p")
    options_formatted = opts.format(
        mediaTitle=title,
        filename=filename,
        refURL=ref
    )
    command = f'"{YTDLP_CMD}" {options_formatted} "{url}"'
    print(f'[{logTime()}]\n    {command}')
    run(command)
    return None

syllabus_as_list = list(syllabus_dict.items())[START:]

print('Start: ' + logTime() + '\n')
startTime, lesson = syllabus_as_list.pop(0)
mediaTitle, refURL = get_params(lesson)
lesson_json = get_json_decoded(refURL)
COURSE_CODE = lesson_json['sectionInfo']['course']['courseIdentifier']
options = ' '.join([
    OPTIONS_CONSTANT.format(course_code=COURSE_CODE),
    '--replace-in-metadata "title" "^.*$" "{mediaTitle}"',
    '-o "{filename}.mp4"',
    '--referer "{refURL}"'
])
videoURL = get_videoURL(lesson_json)
counter = START + 1
download(st=startTime, idx=counter, opts=options, title=mediaTitle, ref=refURL, url=videoURL)

for startTime, lesson in syllabus_as_list:
    counter += 1
    if len(lesson["medias"]) == 0: continue
    mediaTitle, refURL = get_params(lesson)
    videoURL = get_videoURL(get_json_decoded(refURL))
    download(st=startTime, idx=counter, opts=options, title=mediaTitle, ref=refURL, url=videoURL)

print('\nFinish: ' + logTime())