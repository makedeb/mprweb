#!/usr/bin/env python3

import sys
from xml.etree.ElementTree import Element

import bleach
import markdown
import pygit2
from bs4 import BeautifulSoup

import aurweb.config
from aurweb import db, logging, util
from aurweb.models import PackageComment

logger = logging.get_logger(__name__)


class LinkifyExtension(markdown.extensions.Extension):
    """
    Turn URLs into links, even without explicit markdown.
    Do not linkify URLs in code blocks.
    """

    # Captures http(s) and ftp URLs until the first non URL-ish character.
    # Excludes trailing punctuation.
    _urlre = (
        r"(\b(?:https?|ftp):\/\/[\w\/\#~:.?+=&%@!\-;,]+?"
        r"(?=[.:?\-;,]*(?:[^\w\/\#~:.?+=&%@!\-;,]|$)))"
    )

    def extendMarkdown(self, md):
        processor = markdown.inlinepatterns.AutolinkInlineProcessor(self._urlre, md)
        # Register it right after the default <>-link processor (priority 120).
        md.inlinePatterns.register(processor, "linkify", 119)


class FlysprayLinksInlineProcessor(markdown.inlinepatterns.InlineProcessor):
    """
    Turn Flyspray task references like FS#1234 into links to bugs.archlinux.org.

    The pattern's capture group 0 is the text of the link and group 1 is the
    Flyspray task ID.
    """

    def handleMatch(self, m, data):
        el = Element("a")
        el.set("href", f"https://bugs.archlinux.org/task/{m.group(1)}")
        el.text = markdown.util.AtomicString(m.group(0))
        return (el, m.start(0), m.end(0))


class FlysprayLinksExtension(markdown.extensions.Extension):
    def extendMarkdown(self, md):
        processor = FlysprayLinksInlineProcessor(r"\bFS#(\d+)\b", md)
        md.inlinePatterns.register(processor, "flyspray-links", 118)


class HeadingTreeprocessor(markdown.treeprocessors.Treeprocessor):
    def run(self, doc):
        for elem in doc:
            if elem.tag == "h1":
                elem.tag = "h5"
            elif elem.tag in ["h2", "h3", "h4", "h5"]:
                elem.tag = "h6"


class HeadingExtension(markdown.extensions.Extension):
    def extendMarkdown(self, md):
        # Priority doesn't matter since we don't conflict with other processors.
        md.treeprocessors.register(HeadingTreeprocessor(md), "heading", 30)


# Convert standard codeblocks into ones with clipboard copy links.
# This would be a markdown extension, but it doesn't want to work there for some reason.
def ClipboardOnCodeBlock(text):
    soup = BeautifulSoup(text, "html.parser")
    code_blocks = soup.find_all("pre")

    for code_block in code_blocks:
        with open("/aurweb/templates/svg/clipboard.svg", "r") as file:
            clipboard_svg = BeautifulSoup(file.read(), "html.parser")

        with open("/aurweb/templates/svg/check.svg", "r") as file:
            check_svg = BeautifulSoup(file.read(), "html.parser")

        code_block_wrapper = soup.new_tag("div")
        code_block_wrapper["class"] = "code-block"

        clipboard_icons = soup.new_tag("div")
        clipboard_icons["class"] = "clipboard-icons"
        clipboard_icons.append(clipboard_svg)
        clipboard_icons.append(check_svg)

        code_block.wrap(code_block_wrapper)
        code_block.insert_before(clipboard_icons)

    return str(soup)


def save_rendered_comment(comment: PackageComment, html: str):
    with db.begin():
        comment.RenderedComment = html


def update_comment_render_fastapi(comment: PackageComment) -> None:
    update_comment_render(comment)


def update_comment_render(comment: PackageComment) -> None:
    text = comment.Comments
    pkgbasename = comment.PackageBase.Name

    html = markdown.markdown(
        text,
        extensions=[
            "fenced_code",
            LinkifyExtension(),
            FlysprayLinksExtension(),
            HeadingExtension(),
        ],
    )

    allowed_tags = bleach.sanitizer.ALLOWED_TAGS + [
        "p",
        "pre",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
    ]
    bleach.sanitizer.ALLOWED_ATTRIBUTES["code"] = ["class"]

    html = bleach.clean(
        html, tags=allowed_tags, attributes=bleach.sanitizer.ALLOWED_ATTRIBUTES
    )

    for func in [ClipboardOnCodeBlock]:
        html = func(html)

    save_rendered_comment(comment, html)
    db.refresh(comment)


def main():
    db.get_engine()
    comment_id = int(sys.argv[1])
    comment = db.query(PackageComment).filter(PackageComment.ID == comment_id).first()
    update_comment_render(comment)


if __name__ == "__main__":
    main()
