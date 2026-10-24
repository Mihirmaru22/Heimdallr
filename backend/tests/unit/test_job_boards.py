"""Job boards a company's site links to, and their open jobs read through each board's public API."""

import pytest

from app.evidence.jobs import Board, find_boards, read_board

PAGE = """<a href="https://boards.greenhouse.io/acme/jobs/123">Job</a>
<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>
<a href="https://jobs.lever.co/acme-eng">Lever</a> <a href="https://jobs.eu.lever.co/acme-de">EU</a>
<a href="https://jobs.ashbyhq.com/acme">Ashby</a> <a href="https://careers.smartrecruiters.com/AcmeInc">SR</a>
<a href="https://apply.workable.com/acme-ltd/">Workable</a> <a href="https://apply.workable.com/api/v1/x">api</a>"""

RESPONSES = {
    "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true": {"jobs": [
        {"title": "PLM Administrator", "content": "&lt;p&gt;You will run our &lt;b&gt;Teamcenter&lt;/b&gt; "
                                                   "landscape.&lt;/p&gt;",
         "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "updated_at": "2026-09-01T10:00:00-04:00"}]},
    "https://api.lever.co/v0/postings/acme-eng?mode=json&limit=200": [
        {"text": "CAD Engineer", "descriptionPlain": "Design parts.", "createdAt": 1767225600000,
         "lists": [{"text": "Requirements", "content": "<li>Teamcenter experience</li>"}],
         "hostedUrl": "https://jobs.lever.co/acme-eng/2"}],
    "https://api.eu.lever.co/v0/postings/acme-de?mode=json&limit=200": [],
    "https://api.ashbyhq.com/posting-api/job-board/acme": {"jobs": [
        {"title": "SAP Lead", "descriptionPlain": "Own our SAP S/4HANA roadmap.", "publishedAt": "2026-08-01T00:00:00Z",
         "jobUrl": "https://jobs.ashbyhq.com/acme/3"}]},
    "https://api.smartrecruiters.com/v1/companies/AcmeInc/postings?limit=100": {"content": [
        {"id": "744", "name": "ERP Analyst", "releasedDate": "2026-07-15T00:00:00.000Z"}]},
    "https://api.smartrecruiters.com/v1/companies/AcmeInc/postings/744": {
        "postingUrl": "https://jobs.smartrecruiters.com/AcmeInc/744", "jobAd": {"sections": {
            "jobDescription": {"title": "Job", "text": "<p>Support NetSuite users.</p>"}}}},
    "https://apply.workable.com/api/v1/widget/accounts/acme-ltd?details=true": {"jobs": [
        {"title": "Engineer", "description": "<p>We use SolidWorks.</p>", "url": "https://apply.workable.com/j/AB",
         "published_on": "2026-06-30"}]},
}


async def fetch(url):
    if url not in RESPONSES:
        raise LookupError(url)
    return RESPONSES[url]


def test_boards_are_found_in_links_and_embeds_once_each():
    assert find_boards(PAGE) == [Board("Greenhouse", "acme"), Board("Lever", "acme-eng"), Board("Lever EU", "acme-de"),
                                 Board("Ashby", "acme"), Board("SmartRecruiters", "AcmeInc"),
                                 Board("Workable", "acme-ltd")]


@pytest.mark.parametrize("board,title,phrase,url,day", [
    (Board("Greenhouse", "acme"), "PLM Administrator", "You will run our Teamcenter landscape.",
     "https://boards.greenhouse.io/acme/jobs/1", "2026-09-01"),
    (Board("Lever", "acme-eng"), "CAD Engineer", "Requirements: Teamcenter experience",
     "https://jobs.lever.co/acme-eng/2", "2026-01-01"),
    (Board("Ashby", "acme"), "SAP Lead", "Own our SAP S/4HANA roadmap.", "https://jobs.ashbyhq.com/acme/3",
     "2026-08-01"),
    (Board("SmartRecruiters", "AcmeInc"), "ERP Analyst", "Support NetSuite users.",
     "https://jobs.smartrecruiters.com/AcmeInc/744", "2026-07-15"),
    (Board("Workable", "acme-ltd"), "Engineer", "We use SolidWorks.", "https://apply.workable.com/j/AB",
     "2026-06-30"),
])
async def test_each_board_api_becomes_plain_text_jobs(board, title, phrase, url, day):
    (job,) = await read_board(board, fetch)
    assert job.title == title and phrase in job.text and "<" not in job.text
    assert job.url == url and job.date == day


async def test_an_unreadable_board_raises_for_the_caller_to_report():
    with pytest.raises(LookupError):
        await read_board(Board("Greenhouse", "nobody"), fetch)
