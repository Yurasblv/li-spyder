import hashlib
import json
import logging
import os
import re
import time
import random
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

out_dir = Path(__file__).parent / "out"
out_dir.mkdir(parents=True , exist_ok=True)
logging.basicConfig(
    level=logging.INFO ,
    format="%(asctime)s - %(levelname)s - %(message)s" ,
    datefmt="%Y-%m-%d %H:%M:%S" ,
    handlers=[
        logging.FileHandler("out/run.log") ,
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def err_handler(r=""):
    def decorator(f):
        def wrapper(self, *args, **kwargs):
            try:
                return f(self, *args, **kwargs)
            except Exception:
                return r
        return wrapper
    return decorator

class LinkedinSpider:
    def __init__(self , login: str , password: str , min_posts: int) -> None:
        self.login = login
        self.password = password
        self.timeout = 5_000
        self.profile_url = 'https://www.linkedin.com/in/juansebastianmd/'
        self.min_posts = min_posts
        self.results_path = os.path.join(out_dir , "li_posts.json")

        self.user_data_dir = Path(__file__).parent / "_user_data"
        self.user_data_dir.mkdir(exist_ok=True)

    def sleep(self) -> None:
        delay = random.uniform(0.1 , 0.4)
        time.sleep(delay)

    def get_post_id(self, li_tag) -> str:
        urn = li_tag.get_attribute('data-urn')
        return urn or hashlib.md5(li_tag.inner_text().encode()).hexdigest()[:8]

    @err_handler(r="")
    def get_author(self , li_tag) -> str:
        a = li_tag.query_selector('a.update-components-actor__meta-link')
        return a.get_attribute('href')

    @err_handler(r="undefined")
    def get_time(self , li_tag):
        t = li_tag.query_selector('span.update-components-actor__sub-description > span:nth-of-type(1)')
        return t.text_content().strip()

    @err_handler(r="")
    def get_text(self, li_tag) -> str:
        html = li_tag.query_selector('div[dir="ltr"]').text_content().strip()
        html = re.sub(r'<!---->' , '' , html)
        html = re.sub(r'<br\s*/?>' , '\n' , html)
        text = re.sub(r'<[^>]+>' , '' , html)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    @err_handler(r=[])
    def get_tags(self , li_tag) -> list:
        return re.findall(r"#\w+" , li_tag.inner_text())

    @err_handler(r=[])
    def get_links(self , li_tag):
        return re.findall(r"https?://[^\s\"'>]+" , li_tag.inner_text())

    @err_handler(r=0)
    def get_reactions(self , li_tag) -> int:
        if r := li_tag.query_selector('span.social-details-social-counts__reactions-count'):
            value = r.text_content().strip()
            return int(value.replace("\xa0" , "")) if value else 0
        return 0

    @err_handler(r=0)
    def get_comments(self , li_tag) -> int:
        if c := li_tag.query_selector('li.social-details-social-counts__comments > button > span'):
            value = c.text_content().strip()
            match = re.search(r'\d+' , value)
            return int(match.group()) if match else 0
        return 0

    def _auth(self, ctx , page) -> None:
        storage_file = self.user_data_dir / "_ctx.json"

        if not storage_file.exists():
            logger.info("No existing session found. Logging in...")
            page.goto("https://www.linkedin.com/login" , timeout=self.timeout)
            self.sleep()

            page.fill('input[name="session_key"]' , self.login)
            page.fill('input[name="session_password"]' , self.password)
            page.click('button[type="submit"]')

            try:
                page.wait_for_selector('div.feed-shared-update-v2', timeout=self.timeout)

            except Exception as e:
                logger.error("Login failed. Check credentials or connectivity.")
                raise e

            ctx.storage_state(path=str(storage_file))
            logger.info("Login successful. Session saved.")

        else:
            logger.info("Existing session found. Using saved credentials.")

    def run(self) -> None:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                executable_path="" , # WARN: Set default path to chromium/chrome
                user_data_dir=self.user_data_dir,
                headless=False,
            )
            page = ctx.new_page()
            try:

                self._auth(ctx, page)
                self.sleep()

                page.goto(self.profile_url , timeout=self.timeout)
                self.sleep()

                page.click('a[href*="/recent-activity/"]')
                self.sleep()

                start = time.time()
                posts = []

                while len(posts) < self.min_posts and time.time() - start < 60:
                    s = 'div.scaffold-finite-scroll__content > ul > li'
                    page.wait_for_selector(s , timeout=self.timeout, state='visible')
                    li_tags = page.query_selector_all("div[role='article']")

                    logger.info(f"Scrolling to last visible post (total found: {len(li_tags)})")

                    li_tags[-1].scroll_into_view_if_needed(timeout=1000)
                    self.sleep()

                    for idx in range(len(posts), len(li_tags)):
                        li_tag = li_tags[idx]
                        post_id = self.get_post_id(li_tag)
                        text = self.get_text(li_tag)

                        posts.append({
                            "id": post_id ,
                            "author": self.get_author(li_tag) ,
                            "time": self.get_time(li_tag) ,
                            "links": self.get_links(li_tag) ,
                            "text": text,
                            "tags": self.get_tags(li_tag) ,
                            "reactions": self.get_reactions(li_tag) ,
                            "comments": self.get_comments(li_tag)
                        })
                        logger.info(f"Collected post {idx + 1}: {post_id}, {len(text)} chars")

                    time.sleep(random.randint(1,3))

                with open(self.results_path, "w" , encoding="utf-8") as f:
                    json.dump(
                        dict(
                            profile_url=self.profile_url,
                            fetched_at=datetime.now(timezone.utc).isoformat(),
                            total_posts=len(posts),
                            posts=posts,
                        ),
                        f,
                        ensure_ascii=False,
                        indent=4
                )
                logger.info(f"Extraction finished. Total posts collected: {len(posts)}")

            except Exception as e:
                logger.error("Error during scraping: %s" , e)
            finally:
                ctx.close()


if __name__ == "__main__":
    login = input("Enter your linkedin login: ")
    password = input("Enter your linkedin password: ")
    min_posts = input("Min posts amount: ")

    if not min_posts or not min_posts.isdigit():
        min_posts = 10

    spider = LinkedinSpider(login=login, password=password, min_posts=int(min_posts))
    spider.run()
