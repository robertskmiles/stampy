from __future__ import annotations

from dataclasses import dataclass
import re
from typing import cast, Literal, Optional, Union

from api.coda import CodaAPI, QuestionStatus

coda_api = CodaAPI.get_instance()
status_shorthands = coda_api.get_status_shorthand_dict()
all_tags = coda_api.get_all_tags()

status_pat = "|".join(rf"\b{s}\b" for s in status_shorthands).replace(" ", r"\s")

###################################################
#   Parsing query information from message text   #
###################################################


def parse_status(
    text: str, *, require_status_prefix: bool = True
) -> Optional[QuestionStatus]:
    status_prefix = r"status\s*" if require_status_prefix else ""
    re_status = re.compile(
        rf"{status_prefix}({status_pat})",
        re.I | re.X,
    )
    if not (match := re_status.search(text)):
        return
    val = match.group(1)
    return status_shorthands[val.lower()]


def parse_gdoc_links(text: str) -> list[str]:
    """Extract GDoc links from message content.
    Returns `[]` if message doesn't contain any GDoc link.
    """
    return re.findall(r"https://docs\.google\.com/document/d/[\w_-]+", text)


def parse_tag(text: str) -> Optional[str]:
    """Parse string of tags extracted from message"""
    tag_group = (
        "(" + "|".join(all_tags).replace(" ", r"\s") + ")"
    )  # this \s may not be necessary (?)
    re_tag = re.compile(r"tag(?:s|ged(?:\sas)?)?\s+" + tag_group, re.I)
    if (match := re_tag.search(text)) is None:
        return None
    tag = match.group(1)
    tag_group = tag_group.replace(r"\s", " ")
    tag_idx = tag_group.lower().find(tag.lower())
    tag = tag_group[tag_idx : tag_idx + len(tag)]
    return tag


def parse_questions_limit(text: str) -> int:
    re_pre = re.compile(r"(\d{1,2})\sq(?:uestions?)?", re.I)
    re_post = re.compile(r"n\s?=\s?(\d{1,2})", re.I)
    if (match := (re_pre.search(text) or re_post.search(text))) and (
        num := match.group(1)
    ).isdigit():
        return int(num)
    return 1


def parse_question_id(text: str) -> Optional[str]:
    """Parse question id from message content"""
    # matches: "id: <question-id>"
    if match := re.search(r"\sid:?\s+([-\w]+)", text, re.I):
        return match.group(1)
    # matches: "i-<letters-and-numbers-unitl-word-boundary>" (i.e. question id)
    if match := re.search(r"(i-[\w\d]+)\b", text, re.I):
        return match.group(1)


def parse_question_title(text: str) -> Optional[str]:
    if not (match := re.search(r"(?:question):?\s+([-\w\s]+)", text, re.I)):
        return
    question_title = match.group(1)
    return question_title


def parse_question_filter_data(text: str) -> QuestionFilterData:
    return QuestionFilterData(
        status=parse_status(text),
        tag=parse_tag(text),
        limit=parse_questions_limit(text),
    )


###########################
#   QuestionRequestData   #
###########################


def parse_question_request_data(text: str) -> QuestionRequestData:
    if match := re.search(r"(?:get|post) (last|it)", text, re.I):
        mention = cast(Literal["last", "it"], match.group(1))
        return QuestionLast(mention)
    if question_id := parse_question_id(text):
        return QuestionId(question_id)
    if gdoc_links := parse_gdoc_links(text):
        return QuestionGDocLinks(gdoc_links)
    if question_title := parse_question_title(text):
        return QuestionTitle(question_title)
    return parse_question_filter_data(text)


@dataclass(frozen=True)
class QuestionId:
    id: str


@dataclass(frozen=True)
class QuestionGDocLinks:
    links: list[str]


@dataclass(frozen=True)
class QuestionTitle:
    title: str


@dataclass(frozen=True)
class QuestionLast:
    mention: Literal["last", "it"]


@dataclass(frozen=True)
class QuestionNext:
    pass


@dataclass(frozen=True)
class QuestionFilterData:
    status: Optional[QuestionStatus]
    tag: Optional[str]
    limit: int


QuestionRequestData = Union[
    QuestionId,
    QuestionGDocLinks,
    QuestionTitle,
    QuestionLast,
    QuestionFilterData,
]

QuestionPostRequestData = Union[QuestionRequestData, QuestionNext]
