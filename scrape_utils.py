import logging
import time
import urllib.parse
from collections import deque

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
from action_utils import (
    convert_date,
    expand_collapsed_by_xpath,
    find_element_by_xpath,
    find_elements_by_xpath,
    get_anchor_link,
    get_text,
    show_more,
)


def scrape_attachments(driver, dialog_box):
    # Attachment count
    attachment_count_xpath = "(.//span[contains(@class, 'attachment-count')])[last()]"
    attachment_count = find_element_by_xpath(dialog_box, attachment_count_xpath)

    if not attachment_count or not attachment_count.text.strip():
        return None

    # Navigate to attachments page
    attachment_xpath = "//li[@aria-label='Attachments']"
    attachment_button = find_elements_by_xpath(dialog_box, attachment_xpath)
    attachment_button[-1].click()

    # Retrieve attachment links
    attachments_data = []

    attachment_rows = find_elements_by_xpath(
        dialog_box,
        "(.//div[@class='grid-content-spacer'])[last()]/parent::div//div[@role='row']",
    )

    a_href_xpath = ".//div[contains(@class, 'attachments-grid-file-name')]//a"
    date_attached_xpath = ".//div[3]"
    attachments = []

    for attachment in attachment_rows:
        attachment_href = find_element_by_xpath(attachment, a_href_xpath)
        attachment_url = attachment_href.get_attribute("href")
        date_attached = find_element_by_xpath(attachment, date_attached_xpath)

        parsed_url = urllib.parse.urlparse(attachment_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        updated_at = convert_date(date_attached.text, date_format="%d/%m/%Y %H:%M")
        resource_id = parsed_url.path.split("/")[-1]

        file_name = query_params.get("fileName")[0]
        new_file_name = f"{updated_at}_{resource_id}_{file_name}"

        query_params["fileName"] = [new_file_name]
        updated_url = urllib.parse.urlunparse(
            parsed_url._replace(query=urllib.parse.urlencode(query_params, doseq=True))
        )
        attachments_data.append({"url": updated_url, "filename": new_file_name})
        attachments.append(updated_url)

    deque(map(driver.get, attachments))

    # Navigate back to details
    details_tab_xpath = "//li[@aria-label='Details']"
    details_tab_button = find_elements_by_xpath(dialog_box, details_tab_xpath)
    details_tab_button[-1].click()

    return attachments_data


def scrape_history(dialog_box):
    results = []

    # Check if there are collapsed history items
    expand_collapsed_by_xpath(dialog_box)

    history_container_xpath = (
        "(//div[contains(@class, 'workitem-history-control-container')])[last()]"
    )

    history_items = find_elements_by_xpath(
        dialog_box,
        f"{history_container_xpath}//div[@class='history-item-summary-details']",
    )

    for history in history_items:
        history.click()

        details_panel_xpath = (
            f"{history_container_xpath}//div[@class='history-details-panel']"
        )

        result = {
            "User": get_text(
                dialog_box,
                f"{details_panel_xpath}//span[contains(@class, 'history-item-name-changed-by')]",
            ),
            "Date": get_text(
                dialog_box,
                f"{details_panel_xpath}//span[contains(@class, 'history-item-date')]",
            ),
            "Title": get_text(
                dialog_box,
                f"{details_panel_xpath}//div[contains(@class, 'history-item-summary-text')]",
            ),
            "Content": None,
            "Links": [],
            "Fields": [],
        }

        # Get all field changes
        if fields := find_elements_by_xpath(
            dialog_box, f"{details_panel_xpath}//div[@class='field-name']"
        ):
            for field in fields:
                field_name = get_text(field, ".//span")
                field_value = find_element_by_xpath(field, "./following-sibling::div")
                old_value = get_text(field_value, ".//span[@class='field-old-value']")
                new_value = get_text(field_value, ".//span[@class='field-new-value']")

                result["Fields"].append(
                    {"name": field_name, "old_value": old_value, "new_value": new_value}
                )

        if html_field := find_elements_by_xpath(
            dialog_box,
            f"{details_panel_xpath}//div[@class='html-field-name history-section']",
        ):
            for field in html_field:
                field_name = get_text(
                    field,
                    f"{details_panel_xpath}//div[@class='html-field-name history-section']",
                )
                field_value = find_element_by_xpath(
                    field, "//parent::div/following-sibling::div"
                )
                old_value = get_text(
                    field_value, "//span[@class='html-field-old-value']"
                )
                new_value = get_text(
                    field_value, "//span[@class='html-field-new-value']"
                )

                result["Fields"].append(
                    {"name": field_name, "old_value": old_value, "new_value": new_value}
                )

        # Get comments
        if comment := get_text(
            dialog_box,
            f"{details_panel_xpath}//div[contains(@class, 'history-item-comment')]",
        ):
            result["Content"] = comment

        # Get Links
        if links := find_elements_by_xpath(
            dialog_box, f"{details_panel_xpath}//div[@class='history-links']"
        ):
            for link in links:
                result["Links"].append(
                    {
                        "Type": get_text(
                            link, ".//span[contains(@class, 'link-display-name')]//span"
                        ),
                        "Link to item file": get_anchor_link(
                            link, ".//span[contains(@class, 'link-text')]//a"
                        ),
                        "Title": get_text(
                            link, ".//span[contains(@class, 'link-text')]//span"
                        ),
                    }
                )

        results.append(result)

    return results


def scrape_related_work(driver, dialog_box):
    results = []

    related_work_xpath = "(.//div[@class='links-control-container']/div[@class='la-main-component'])[last()]"
    show_more_xpath = "//div[@class='la-show-more']"
    show_more(dialog_box, f"{related_work_xpath}{show_more_xpath}")

    related_work_items = find_elements_by_xpath(
        dialog_box, f"{related_work_xpath}/div[@class='la-list']/div"
    )

    if not related_work_items:
        return results

    for related_work_item in related_work_items:
        related_work_type_xpath = "div[@class='la-group-title']"
        related_work_type = find_element_by_xpath(
            related_work_item, related_work_type_xpath
        )

        related_work_type = related_work_type.text
        related_work_type = related_work_type.split(" ")[0]
        result = {"type": related_work_type, "related_work_items": []}

        related_works_xpath = "div[@class='la-item']"
        related_works = find_elements_by_xpath(related_work_item, related_works_xpath)

        updated_at_hover_xpath = (
            "div/div/div[@class='la-additional-data']/div[1]/div/span"
        )

        for related_work in related_works:
            related_work_link = find_element_by_xpath(related_work, "div/div/div//a")

            updated_at_hover = find_element_by_xpath(
                related_work, updated_at_hover_xpath
            )
            updated_at = None
            retry_count = 0

            while updated_at is None and retry_count < config.MAX_RETRIES:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('mouseover', {'bubbles': true}));",
                    updated_at_hover,
                )
                updated_at = get_text(driver, "//p[contains(text(), 'Updated by')]")
                retry_count += 1
                print(
                    f"Retrying hover on work related date ... {retry_count}/{config.MAX_RETRIES}"
                )
                time.sleep(3)

            logging.info(f"related work item '{updated_at}'")

            driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('mouseout', {'bubbles': true}));",
                updated_at_hover,
            )

            related_work_item_id = related_work_link.get_attribute("href").split("/")[
                -1
            ]
            related_work_title = related_work_link.text.replace(" ", "_")
            result["related_work_items"].append(
                {
                    "filename_source": f"{related_work_item_id}_{related_work_title}",
                    "link_target": f"{related_work_item_id}_{related_work_title}_update_{convert_date(updated_at)}_{related_work_type}",
                    "updated_at": " ".join(updated_at.split(" ")[-4:]),
                }
            )

        results.append(result)

    return results


def scrape_discussion_attachments(driver, attachment, discussion_date):
    parsed_url = urllib.parse.urlparse(attachment.get_attribute("src"))
    query_params = urllib.parse.parse_qs(parsed_url.query)
    discussion_date = convert_date(discussion_date)
    resource_id = parsed_url.path.split("/")[-1]

    file_name = query_params.get("fileName")[0]
    new_file_name = f"{discussion_date}_{resource_id}_{file_name}"

    query_params["fileName"] = [new_file_name]

    if "download" not in query_params:
        query_params["download"] = "True"

    updated_url = urllib.parse.urlunparse(
        parsed_url._replace(query=urllib.parse.urlencode(query_params, doseq=True))
    )
    driver.get(updated_url)

    return {"url": updated_url, "filename": query_params["fileName"][0]}


def scrape_discussions(driver):
    results = []

    dialog_xpath = "//div[@role='dialog'][last()]"

    discussions_xpath = (
        f"{dialog_xpath}//div[contains(@class, 'initialized work-item-discussion-control')]"
        "//div[contains(@class, 'wit-comment-item')]"
    )
    discussions = find_elements_by_xpath(driver, discussions_xpath)

    if discussions:
        for discussion in discussions:
            content_xpath = ".//div[@class='comment-content']"
            content = get_text(discussion, content_xpath)

            content_attachment_xpath = f"{content_xpath}//img"
            attachments = find_elements_by_xpath(discussion, content_attachment_xpath)
            comment_timestamp = find_element_by_xpath(
                discussion, ".//a[@class='comment-timestamp']"
            )
            date = None
            retry_count = 0

            while date is None and retry_count < config.MAX_RETRIES:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('mouseover', {'bubbles': true}));",
                    comment_timestamp,
                )
                date = get_text(
                    discussion, "//p[contains(@class, 'ms-Tooltip-subtext')]"
                )
                retry_count += 1
                print(
                    f"Retrying hover on discussion date ... {retry_count}/{config.MAX_RETRIES}"
                )
                time.sleep(3)

            html_source = driver.execute_script(
                "return document.getElementsByTagName('html')[0].innerHTML"
            )
            log_html(html_source, "discussion_date.log")
            logging.info(f"discussion date '{date}'")

            driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('mouseout', {'bubbles': true}));",
                comment_timestamp,
            )

            discussion_date = " ".join(date.split(" ")[-4:])

            result = {
                "User": get_text(discussion, ".//span[@class='user-display-name']"),
                "Content": content,
                "Date": discussion_date,
                "attachments": [
                    scrape_discussion_attachments(driver, attachment, discussion_date)
                    for attachment in (attachments or [])
                ],
            }
            results.append(result)
    return results


def scrape_changesets(driver):
    results = []

    files_changed = find_elements_by_xpath(driver, "//tr[@role='treeitem']")

    for file in files_changed:
        file.click()

        header_xpath = "//span[@role='heading']"

        result = {
            "File Name": get_text(driver, header_xpath),
            "Path": get_text(
                driver, f"{header_xpath}/parent::span/following-sibling::span"
            ),
            "content": get_text(
                driver,
                "(//div[contains(@class,'lines-content')])[last()]",
            ),
        }

        results.append(result)
    return results


def scrape_development(driver):
    results = []

    development_links = find_elements_by_xpath(
        driver,
        f"//div[@role='dialog'][last()]//span[@aria-label='Development section.']/ancestor::div[@class='grid-group']//a",
    )

    original_window = driver.current_window_handle

    if development_links:
        for development_link in development_links:
            development_link.click()

            WebDriverWait(driver, config.MAX_WAIT_TIME).until(
                EC.number_of_windows_to_be(2)
            )

            driver.switch_to.window(driver.window_handles[-1])
            result = {
                "ID": driver.current_url.split("/")[-1],
                "Title": driver.title,
                "change_sets": scrape_changesets(driver),
            }
            results.append(result)

            driver.close()
            driver.switch_to.window(original_window)
    return results


def scrape_description(element):
    html = element.get_attribute("innerHTML")
    return html


def log_html(page_source, log_file_path="source.log"):
    with open(log_file_path, "w", encoding="utf-8") as file:
        file.write(page_source)
