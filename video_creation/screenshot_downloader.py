import json
import re
from pathlib import Path
from typing import Dict, Final

import translators
from playwright.sync_api import ViewportSize, sync_playwright
from rich.progress import track

from utils import settings
from utils.console import print_step, print_substep
from utils.imagenarator import imagemaker
from utils.playwright import clear_cookie_by_name
from utils.videos import save_data

__all__ = ["get_screenshots_of_reddit_posts"]


def get_screenshots_of_reddit_posts(reddit_object: dict, screenshot_num: int):
    """Downloads screenshots of reddit posts as seen on the web. Downloads to assets/temp/png

    Args:
        reddit_object (Dict): Reddit object received from reddit/subreddit.py
        screenshot_num (int): Number of screenshots to download
    """
    # settings values
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    lang: Final[str] = settings.config["reddit"]["thread"]["post_lang"]
    storymode: Final[bool] = settings.config["settings"]["storymode"]

    print_step("Downloading screenshots of reddit posts...")
    reddit_id = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])
    # ! Make sure the reddit screenshots folder exists
    Path(f"assets/temp/{reddit_id}/png").mkdir(parents=True, exist_ok=True)

    # set the theme and disable non-essential cookies
    if settings.config["settings"]["theme"] == "dark":
        cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        bgcolor = (33, 33, 36, 255)
        txtcolor = (240, 240, 240)
        transparent = False
    elif settings.config["settings"]["theme"] == "transparent":
        if storymode:
            # Transparent theme
            bgcolor = (0, 0, 0, 0)
            txtcolor = (255, 255, 255)
            transparent = True
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        else:
            # Switch to dark theme
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
            bgcolor = (33, 33, 36, 255)
            txtcolor = (240, 240, 240)
            transparent = False
    else:
        cookie_file = open("./video_creation/data/cookie-light-mode.json", encoding="utf-8")
        bgcolor = (255, 255, 255, 255)
        txtcolor = (0, 0, 0)
        transparent = False

    if storymode and settings.config["settings"]["storymodemethod"] == 1:
        # for idx,item in enumerate(reddit_object["thread_post"]):
        print_substep("Generating images...")
        return imagemaker(
            theme=bgcolor,
            reddit_obj=reddit_object,
            txtclr=txtcolor,
            transparent=transparent,
        )

    screenshot_num: int
    with sync_playwright() as p:
        print_substep("Launching Headless Browser...")

        browser = p.chromium.launch(
            headless=True
        )  # headless=False will show the browser for debugging purposes
        # Device scale factor (or dsf for short) allows us to increase the resolution of the screenshots
        # When the dsf is 1, the width of the screenshot is 600 pixels
        # so we need a dsf such that the width of the screenshot is greater than the final resolution of the video
        dsf = (W // 600) + 1

        context = browser.new_context(
            locale=lang or "en-us",
            color_scheme="dark",
            viewport=ViewportSize(width=W, height=H),
            device_scale_factor=dsf,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        )
        cookies = json.load(cookie_file)
        cookie_file.close()

        context.add_cookies(cookies)  # load preference cookies

        # Login to Reddit
        print_substep("Logging in to Reddit...")
        page = context.new_page()
        page.goto("https://www.reddit.com/login", timeout=0)
        page.set_viewport_size(ViewportSize(width=1920, height=1080))
        page.wait_for_load_state()

        page.locator(f'input[name="username"]').fill(settings.config["reddit"]["creds"]["username"])
        page.locator(f'input[name="password"]').fill(settings.config["reddit"]["creds"]["password"])
        page.get_by_role("button", name="Log In").click()
        page.wait_for_timeout(5000)

        login_error_div = page.locator(".AnimatedForm__errorMessage").first
        if login_error_div.is_visible():
            login_error_message = login_error_div.inner_text()
            if login_error_message.strip() == "":
                # The div element is empty, no error
                pass
            else:
                # The div contains an error message
                print_substep(
                    "Your reddit credentials are incorrect! Please modify them accordingly in the config.toml file.",
                    style="red",
                )
                exit()
        else:
            pass

        page.wait_for_load_state()
        # Handle the redesign
        # Check if the redesign optout cookie is set
        if page.locator("#redesign-beta-optin-btn").is_visible():
            # Clear the redesign optout cookie
            clear_cookie_by_name(context, "redesign_optout")
            # Reload the page for the redesign to take effect
            page.reload()
        # Get the thread screenshot
        page.goto(reddit_object["thread_url"], timeout=0)
        page.set_viewport_size(ViewportSize(width=W, height=H))
        page.wait_for_load_state()
        page.wait_for_timeout(5000)

        if page.locator(
            "#t3_12hmbug > div > div._3xX726aBn29LDbsDtzr_6E._1Ap4F5maDtT1E1YuCiaO0r.D3IL3FD0RFy_mkKLPwL4 > div > div > button"
        ).is_visible():
            # This means the post is NSFW and requires to click the proceed button.

            print_substep("Post is NSFW. You are spicy...")
            page.locator(
                "#t3_12hmbug > div > div._3xX726aBn29LDbsDtzr_6E._1Ap4F5maDtT1E1YuCiaO0r.D3IL3FD0RFy_mkKLPwL4 > div > div > button"
            ).click()
            page.wait_for_load_state()  # Wait for page to fully load

            # translate code
        if page.locator(
            "#SHORTCUT_FOCUSABLE_DIV > div:nth-child(7) > div > div > div > header > div > div._1m0iFpls1wkPZJVo38-LSh > button > i"
        ).is_visible():
            page.locator(
                "#SHORTCUT_FOCUSABLE_DIV > div:nth-child(7) > div > div > div > header > div > div._1m0iFpls1wkPZJVo38-LSh > button > i"
            ).click()  # Interest popup is showing, this code will close it

        if lang:
            print_substep("Translating post...")
            texts_in_tl = translators.translate_text(
                reddit_object["thread_title"],
                to_language=lang,
                translator="google",
            )
            page.evaluate(
                """tl_content => {
                    // Try different possible selectors for Reddit post titles
                    const selectors = [
                        // Modern shreddit selectors (new Reddit design)
                        `h1[id^="post-title-t3_"]`,
                        'shreddit-post h1[slot="title"]',
                        // Older selectors
                        '[data-adclicklocation="title"] > div > div > h1',
                        '[data-test-id="post-content"] h1', 
                        '[data-testid="post-content"] h1',
                        'h1[slot="title"]',
                        'div[slot="title"] h1',
                        'div[data-testid="post-container"] h1',
                        'shreddit-title h1'
                    ];
                    
                    let titleElement = null;
                    for (const selector of selectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            titleElement = element;
                            break;
                        }
                    }
                    
                    if (titleElement) {
                        titleElement.textContent = tl_content;
                    } else {
                        console.error('Could not find title element with any known selector');
                    }
                }""",
                texts_in_tl,
            )
        else:
            print_substep("Skipping translation...")

        postcontentpath = f"assets/temp/{reddit_id}/png/title.png"
        try:
            if settings.config["settings"]["zoom"] != 1:
                # store zoom settings
                zoom = settings.config["settings"]["zoom"]
                # zoom the body of the page
                page.evaluate("document.body.style.zoom=" + str(zoom))
                
                # Try multiple selectors for the post content
                selectors = [
                    'shreddit-post',
                    'div[slot="text-body"]',
                    'div[data-test-id="post-content"]',
                    'div[data-testid="post-content"]'
                ]
                
                found_element = False
                for selector in selectors:
                    if page.locator(selector).count() > 0:
                        print_substep(f"Found post content using selector: {selector}")
                        location = page.locator(selector).first.bounding_box()
                        for i in location:
                            location[i] = float("{:.2f}".format(location[i] * zoom))
                        page.screenshot(clip=location, path=postcontentpath)
                        found_element = True
                        break
                
                if not found_element:
                    print_substep("Could not find post content with known selectors, taking screenshot of whole page")
                    page.screenshot(path=postcontentpath)
            else:
                # Try multiple selectors
                selectors = [
                    'shreddit-post',
                    'div[slot="text-body"]',
                    'div[data-test-id="post-content"]',
                    'div[data-testid="post-content"]'
                ]
                
                found_element = False
                for selector in selectors:
                    if page.locator(selector).count() > 0:
                        print_substep(f"Found post content using selector: {selector}")
                        page.locator(selector).first.screenshot(path=postcontentpath)
                        found_element = True
                        break
                
                if not found_element:
                    print_substep("Could not find post content with known selectors, taking screenshot of whole page")
                    page.screenshot(path=postcontentpath)
        except Exception as e:
            print_substep("Something went wrong!", style="red")
            resp = input(
                "Something went wrong with making the screenshots! Do you want to skip the post? (y/n) "
            )

            if resp.casefold().startswith("y"):
                save_data("", "", "skipped", reddit_id, "")
                print_substep(
                    "The post is successfully skipped! You can now restart the program and this post will skipped.",
                    "green",
                )

            resp = input("Do you want the error traceback for debugging purposes? (y/n)")
            if not resp.casefold().startswith("y"):
                exit()

            raise e

        if storymode:
            # Try multiple selectors for story content
            story_selectors = [
                'shreddit-post div[slot="text-body"]',
                'div[slot="text-body"]',
                'div.text-neutral-content',
                '[data-click-id="text"]'
            ]
            
            found_element = False
            for selector in story_selectors:
                if page.locator(selector).count() > 0:
                    print_substep(f"Found story content using selector: {selector}")
                    page.locator(selector).first.screenshot(
                        path=f"assets/temp/{reddit_id}/png/story_content.png"
                    )
                    found_element = True
                    break
            
            if not found_element:
                print_substep("Could not find story content with known selectors, taking screenshot of whole page")
                page.screenshot(path=f"assets/temp/{reddit_id}/png/story_content.png")
        else:
            for idx, comment in enumerate(
                track(
                    reddit_object["comments"][:screenshot_num],
                    "Downloading screenshots...",
                )
            ):
                # Stop if we have reached the screenshot_num
                if idx >= screenshot_num:
                    break

                if page.locator('[data-testid="content-gate"]').is_visible():
                    page.locator('[data-testid="content-gate"] button').click()

                page.goto(f"https://new.reddit.com/{comment['comment_url']}")

                # translate code

                if settings.config["reddit"]["thread"]["post_lang"]:
                    comment_tl = translators.translate_text(
                        comment["comment_body"],
                        translator="google",
                        to_language=settings.config["reddit"]["thread"]["post_lang"],
                    )
                    page.evaluate(
                        """([tl_content, tl_id]) => {
                            // Try different possible selectors for Reddit comments
                            const selectors = [
                                // Modern shreddit selectors (new Reddit design)
                                `shreddit-comment[id="t1_${tl_id}"] .md`,
                                `shreddit-comment[id="t1_${tl_id}"] div[id^="comment-content-"]`,
                                `shreddit-comment[id^="t1_${tl_id}"] div.text-neutral-content`,
                                // Older selectors
                                `#t1_${tl_id} > div:nth-child(2) > div > div[data-testid="comment"] > div`,
                                `#t1_${tl_id} [data-testid="comment"] > div`,
                                `#t1_${tl_id} div[data-testid="comment-top-meta"]`,
                                `[id="t1_${tl_id}"] div[data-testid="comment"]`, 
                                `div[id="t1_${tl_id}"] div[data-testid="comment"]`,
                                `div.comment div[id="t1_${tl_id}"] .md`
                            ];
                            
                            let commentElement = null;
                            for (const selector of selectors) {
                                const element = document.querySelector(selector);
                                if (element) {
                                    commentElement = element;
                                    break;
                                }
                            }
                            
                            if (commentElement) {
                                commentElement.textContent = tl_content;
                            } else {
                                console.error('Could not find comment element with any known selector');
                            }
                        }""",
                        [comment_tl, comment["comment_id"]],
                    )
                try:
                    if settings.config["settings"]["zoom"] != 1:
                        # store zoom settings
                        zoom = settings.config["settings"]["zoom"]
                        # zoom the body of the page
                        page.evaluate("document.body.style.zoom=" + str(zoom))
                        
                        # Try multiple selectors for comment elements
                        selectors = [
                            f"shreddit-comment[id='t1_{comment['comment_id']}']",
                            f"#t1_{comment['comment_id']}",
                            f"div[id='t1_{comment['comment_id']}']"
                        ]
                        
                        found_element = False
                        for selector in selectors:
                            if page.locator(selector).count() > 0:
                                print_substep(f"Found comment using selector: {selector}")
                                # scroll comment into view
                                page.locator(selector).first.scroll_into_view_if_needed()
                                # as zooming the body doesn't change the properties of the divs, we need to adjust for the zoom
                                location = page.locator(selector).first.bounding_box()
                                if location:
                                    for i in location:
                                        location[i] = float("{:.2f}".format(location[i] * zoom))
                                    page.screenshot(
                                        clip=location,
                                        path=f"assets/temp/{reddit_id}/png/comment_{idx}.png",
                                    )
                                    found_element = True
                                    break
                        
                        if not found_element:
                            print_substep(f"Could not find comment {comment['comment_id']} with any selector, taking screenshot of visible area")
                            page.screenshot(path=f"assets/temp/{reddit_id}/png/comment_{idx}.png")
                    else:
                        # Try multiple selectors for comment elements
                        selectors = [
                            f"shreddit-comment[id='t1_{comment['comment_id']}']",
                            f"#t1_{comment['comment_id']}",
                            f"div[id='t1_{comment['comment_id']}']"
                        ]
                        
                        found_element = False
                        for selector in selectors:
                            if page.locator(selector).count() > 0:
                                print_substep(f"Found comment using selector: {selector}")
                                page.locator(selector).first.screenshot(
                                    path=f"assets/temp/{reddit_id}/png/comment_{idx}.png"
                                )
                                found_element = True
                                break
                        
                        if not found_element:
                            print_substep(f"Could not find comment {comment['comment_id']} with any selector, taking screenshot of visible area")
                            page.screenshot(path=f"assets/temp/{reddit_id}/png/comment_{idx}.png")
                except TimeoutError:
                    del reddit_object["comments"]
                    screenshot_num += 1
                    print("TimeoutError: Skipping screenshot...")
                    continue

        # close browser instance when we are done using it
        browser.close()

    print_substep("Screenshots downloaded Successfully.", style="bold green")
