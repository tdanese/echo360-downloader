from pathlib import Path
from subprocess import run
import datetime as dt

def load_cookies(cookie: str) -> dict[str, str]:
    cookiepath = Path(cookie).absolute()
    cookiepath.touch()
    with open(cookiepath, 'rt') as f:
        cookies = f.readlines()
        while len(cookies) <= 1:
            print(f"Please export cookies from your browser with Cookie-Editor, then paste into '{cookiepath}'")
            input("Press Enter to continue...")
            cookies = f.readlines()

    cookie_dict = {}
    for line in cookies:
        if (
            (line.find('\t') > 0)
            and
            (not line.startswith('# '))
            ):
            c = line.strip().split('\t')
            cookie_dict[c[5]] = c[6]
    return cookie_dict

def sanitise_filename(f: str) -> str:
    return f.replace('"', "\u201c"
    ).replace("/", "\u29F8"
    ).replace("\\", "\u29f9"
    ).replace("*", "\uff0a"
    ).replace(":", "\uff1a"
    ).replace('<', "\uff1c"
    ).replace('>', "\uff1e"
    ).replace('?', "\uff1f"
    ).replace('|', "\uff5c"
    )

def logTime() -> str:
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')

def update_exe(yt_dlp_path: str="yt-dlp", deno_path: str="deno", days_since_last_checked: int=14) -> None:
    last_update_path = Path("last_update_check.txt")
    last_update_path.touch()
    fmtStr = '%Y-%m-%d'
    today = dt.datetime.today()
    with open(last_update_path, 'rt') as f:
        last_update = f.read(10)

    last_update_date = dt.datetime.strptime(last_update, fmtStr).date()
    if (
        (len(last_update) < 10)
        or
        ((today.date() - last_update_date) > dt.timedelta(days=days_since_last_checked))
        ):
        print(logTime() + " Checking for updates...")
        run(f'"{yt_dlp_path}" -U')
        run(f'"{deno_path}" upgrade')
        with open(last_update_path, 'wt') as f:
            f.write(today.strftime(fmtStr))
    return None