from bs4 import BeautifulSoup as bs
import requests
from ebooklib import epub
from urllib.parse import urlparse, urljoin

import os

URL_EBOOK_TOC = "http://www.dspguide.com/pdfbook.htm"
parsed = urlparse(URL_EBOOK_TOC)
URL_SERVER = parsed.scheme +  '://' + parsed.netloc
DEFAULT_DIRECTORY = "./ebooks"

progress = 0

def get_contents(url):
    """
    Get the content root from url website.
    """
    req = requests.get(url)
    return bs(req.text, 'lxml', from_encoding='UTF-8')


def get_sections_links(toc_page_contents, url_server):
    """
    Get links of each chapter/section from the table of contents page.

    Return sub sections links, separated in chapters.
    """
    section_links = []

    # Select sections links contents
    toc_contents = toc_page_contents.select('div[id="columnRight"] > ul > li')

    # Get sections
    for sections_block in toc_contents:
        section_text = sections_block.select("a[href]")[0].get_text()

        links = []

        section_links.append({"title": section_text,
                            "links": links})

        # Get all sub sections links in section
        for sub_section in sections_block.select("ul > li"):
            sub_section_refs = sub_section.select("a[href]")

            for ref in sub_section_refs:
                sub_section_title = section_text + " - " + ref.get_text()
                links.append(
                    {"title": sub_section_title,
                    "url": urljoin(url_server, ref["href"])})




    return section_links

def correct_section_contents(section_contents):
    # Remove ads
    for ad in section_contents.select('div[id="adbox"]'):
        ad.extract()

    # Remove duplicated title
    for title in section_contents.select("div.breadcrumbs"):
        title.extract()

    # Retrieve section title
    section_title = section_contents.select("div.subTitle")[0]

    # Replace section/chapter title by sub section title
    title = section_contents.select('h2')[0]
    title.string = section_title.string

    # Remove old section title
    section_title.extract()

    # Remove the next Section
    next_sections = section_contents.findAll(string="Next Section: ")

    # And the specified link
    if len(next_sections) > 0:
        for content in section_contents.contents:
            if hasattr(content, "previous_sibling") and content.previous_sibling in next_sections:
                content.extract()

    for next_section in next_sections:
        next_section.extract()

    return next_sections


def get_image_source_location(img_info, section_link, url_server):
    if img_info["src"].startswith("http"):
        return img_info["src"]
    else:
        if img_info["src"].startswith("/"):
            return urljoin(url_server, img_info["src"])
        else:
            return urljoin(section_link["url"], img_info["src"])


def retrieve_sub_section_images(sub_section_contents, section_index, sub_section_index, sub_section_link, url_server):
    """
    Retrieve images in sub sections.

    Return list of images.
    """

    section_images = []
    for img_index, img_info in enumerate(sub_section_contents.findAll("img")):
        # Get image source location
        image_source_location = get_image_source_location(img_info, sub_section_link, url_server)

        # Load image from the source location
        req = requests.get(image_source_location)

        # If the page exists
        if req.status_code == 200:
            img_extension = img_info['src'].split('.')[-1]
            img_name = 's{}_c{}_i{}.{}'.format(
                str(section_index).zfill(2),
                str(sub_section_index).zfill(2),
                str(img_index).zfill(2),
                img_extension
            )

            img_info['src'] = img_name

            section_images.append(epub.EpubItem(
                file_name=img_name,
                media_type=img_extension,
                content=req.content
            ))
        else:
            img_info["src"] = ""

    return section_images


def retrieve_section_contents(sections_links, url_server):
    """
    Retrieve contents from all sections.

    Return list of sections contents.
    """
    init_retrieve_progress()
    init_section_count(len(sections_links))

    for section_index, section in enumerate(sections_links):
        print_progress("Retrieving " + section["title"])

        section['file_name'] = 's{}.htmlx'.format(str(section_index).zfill(2))
        section['content'] = '<html><head><meta charset="UTF-8"></head><body>' \
                      '{}</body></html>'.format("<h1>" + section["title"] + "</h1>")

        init_sub_section_count(len(section["links"]))
        for sub_section_index, sub_section_link in enumerate(section["links"]):
            print_progress("Retrieving " + sub_section_link["title"])
            page_contents = get_contents(sub_section_link["url"])


            # Select content
            if len(page_contents.select('div[id="columnRight"]')) == 0:
                continue

            section_contents = page_contents.select('div[id="columnRight"]')[0]

            # Remove and replace part of contents
            correct_section_contents(section_contents)

            # Retrieve images
            sections_images = retrieve_sub_section_images(sub_section_contents=section_contents,
                                                          section_index=section_index,
                                                          sub_section_index=sub_section_index,
                                                          sub_section_link=sub_section_link,
                                                          url_server=url_server)

            # Update modified content
            section_contents = '<html><head><meta charset="UTF-8"></head><body>' \
                      '{}</body></html>'.format(section_contents.prettify())

            page_file_name = 's{}_c{}.htmlx'.format(str(section_index).zfill(2),
                                               str(sub_section_index).zfill(2))
            sub_section_link.update({
                'content': section_contents,
                'file_name': page_file_name,
                'images_items': sections_images
            })
            next_sub_section_count()

        next_section_count()


    return sections_links


def create_ebook(sections):
    """
    Create epub ebook from the selected contents.
    """
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier("gtdsp")
    book.set_title("The Scientist and Engineer\'s Guide to Digital Signal Processing")
    book.set_language("en")
    book.add_author("Steven W. Smith")
    book.add_author("Ph.D.")

    # Add default NCX and NAV file
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    toc = []

    # Create the first page
    cover_content = '<html><head><meta charset="UTF-8"></head><body>' \
                         '{}</body></html>'.format("<h1>" + "The Scientist and Engineer\'s Guide to Digital Signal Processing" + "</h1>")
    cover_item = epub.EpubHtml(title="Cover",
                                file_name='cover.htmlx',
                                content=cover_content,
                                media_type = "application/xhtml+xml")

    book.add_item(cover_item)
    toc.append(cover_item)

    # Create toc from sections and sub sections

    for section in sections:
        section_item = epub.EpubHtml(title=section["title"],
                                file_name=section["file_name"],
                                content=section["content"],
                                media_type="application/xhtml+xml")
        book.add_item(section_item)
        toc.append(section_item)
        for sub_section_index, sub_section_link in enumerate(section["links"]):
            title = sub_section_link["title"]
            if sub_section_index > 0:
                title = ' - {}'.format(title)
            sub_section_item = epub.EpubHtml(title=title,
                                    file_name=sub_section_link["file_name"],
                                    content=sub_section_link["content"],
                                    media_type="application/xhtml+xml")

            book.add_item(sub_section_item)
            toc.append(sub_section_item)

            for image_item in sub_section_link["images_items"]:
                book.add_item(image_item)


    # Create table of contents
    book.toc = toc

    # Set spine
    book.spine = toc

    return book


def save_ebook(ebook, directory):
    """
    Save ebook to the desired location.
    """

    # If the location does not exist
    if not os.path.isdir(directory):
        os.mkdir(directory)

    # Save ebook to disk
    epub.write_epub(directory + "/" + ebook.title + ".epub", ebook, {})

def print_progress(msg):
    print(("[ {:3d}% ] - " + msg).format(int(progress)))

def set_progress(_progress):
    global progress
    progress = _progress

def set_count(_count):
    global count
    count = _count

def init_section_count(_section_count):
    global section_count
    global current_section
    global current_sub_section
    section_count = _section_count
    current_section = 0
    current_sub_section = 0

def next_section_count():
    global current_section
    global current_sub_section
    current_sub_section = 0
    current_section += 1
    update_progress()

def init_sub_section_count(_sub_section_count):
    global sub_section_count
    global current_sub_section
    sub_section_count = _sub_section_count
    current_sub_section = 0

def next_sub_section_count():
    global current_sub_section
    current_sub_section += 1
    update_progress()

def init_retrieve_progress():
    global start_progress
    global total_progress
    start_progress = 2
    total_progress = 96

def update_progress():
    global progress
    global current_sub_section
    global sub_section_count
    global current_section
    global section_count
    global start_progress
    global total_progress

    sub_section_progress = ((current_sub_section)/ sub_section_count)
    progress = ((sub_section_progress + current_section) * (total_progress / section_count)) + start_progress


def create_digital_signal_processing_ebook():
    """
    Create dsp epub ebook from digital processing signal website
    """

    print_progress("Starting DSP Ebook creation")
    set_progress(0)
    print_progress("Getting table of contents")
    contents = get_contents(url=URL_EBOOK_TOC)
    set_progress(1)

    print_progress("Getting sections links")
    sections_links = get_sections_links(toc_page_contents=contents,
                                        url_server=URL_SERVER)

    set_progress(2)
    print_progress("Retrieving " + str(len(sections_links)) + " chapters")

    sections = retrieve_section_contents(sections_links=sections_links,
                                         url_server=URL_SERVER)

    set_progress(98)
    print_progress("Creating ebook")
    ebook = create_ebook(sections=sections)

    set_progress(99)
    print_progress("Saving ebook")
    save_ebook(ebook=ebook,
               directory=DEFAULT_DIRECTORY)

    set_progress(100)
    print_progress("Ebook saved: " + DEFAULT_DIRECTORY + "/" + ebook.title + ".epub")

if __name__ == "__main__":
    create_digital_signal_processing_ebook()