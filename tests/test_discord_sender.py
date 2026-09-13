import io
from copy import deepcopy
import http.client
import json
import os
import unittest
import urllib.error
from unittest import mock

import discord_sender


class FakeResponse:
    def __init__(self, status=204):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def http_error(code, body="{}", headers=None):
    return urllib.error.HTTPError(
        "https://discord.invalid/webhook",
        code,
        "test error",
        headers or {},
        io.BytesIO(body.encode("utf-8")),
    )


class DiscordSenderTests(unittest.TestCase):
    def setUp(self):
        self.webhook_patch = mock.patch.object(discord_sender, "WEBHOOK_URL", "")
        self.webhook_patch.start()

    def tearDown(self):
        self.webhook_patch.stop()

    def test_missing_webhook_in_ci_fails(self):
        with mock.patch.dict(os.environ, {"CI": "true"}, clear=True):
            with self.assertRaises(SystemExit) as raised:
                discord_sender.send([])

        self.assertEqual(raised.exception.code, 1)

    def test_console_output_requires_explicit_dry_run(self):
        embed = discord_sender.make_embed("제목", "내용", "header")
        with (
            mock.patch.dict(os.environ, {"DISCORD_DRY_RUN": "1"}, clear=True),
            mock.patch.object(discord_sender.urllib.request, "urlopen") as urlopen,
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            discord_sender.send([embed])

        urlopen.assert_not_called()
        self.assertIn("[DRY RUN]", stdout.getvalue())
        self.assertIn("제목", stdout.getvalue())

    def test_batches_by_ten_embeds_without_dropping_any(self):
        embeds = [discord_sender.make_embed(f"제목 {i}", "내용", "header") for i in range(11)]
        with (
            mock.patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.invalid"}, clear=True),
            mock.patch.object(
                discord_sender.urllib.request,
                "urlopen",
                side_effect=[FakeResponse(), FakeResponse()],
            ) as urlopen,
        ):
            discord_sender.send(embeds)

        self.assertEqual(urlopen.call_count, 2)
        payloads = [json.loads(call.args[0].data) for call in urlopen.call_args_list]
        self.assertEqual([len(payload["embeds"]) for payload in payloads], [10, 1])
        self.assertEqual(sum(len(payload["embeds"]) for payload in payloads), 11)

    def test_batches_by_total_character_limit(self):
        embeds = [discord_sender.make_embed(str(i), "x" * 2500, "header") for i in range(3)]

        batches = discord_sender._batch_embeds(embeds)

        self.assertEqual([len(batch) for batch in batches], [2, 1])
        for batch in batches:
            self.assertLessEqual(
                sum(discord_sender._embed_char_count(embed) for embed in batch),
                discord_sender.MAX_EMBED_CHARS_PER_MESSAGE,
            )

    def test_make_embed_keeps_deadlines_and_source_links_after_limit(self):
        description = "공지 내용\n" * 1500 + "\n오늘 18:00 마감\n[원문](https://example.com/notice)"
        embed = discord_sender.make_embed("학사 공지", description, "notice")

        pages = discord_sender.prepare_embeds([embed])

        self.assertEqual(embed["description"], description)
        self.assertGreater(len(pages), 1)
        self.assertEqual("".join(page["description"] for page in pages), description)
        self.assertIn("오늘 18:00 마감", pages[-1]["description"])
        self.assertIn("[원문](https://example.com/notice)", pages[-1]["description"])
        for index, page in enumerate(pages, 1):
            self.assertEqual(page["title"], f"학사 공지 · {index}/{len(pages)}")
            self.assertLessEqual(discord_sender._text_length(page["description"]), 4096)

    def test_pages_prefer_paragraph_then_line_boundaries(self):
        for separator in ("\n\n", "\n"):
            with self.subTest(separator=repr(separator)):
                first = "가" * 1500 + separator + "나" * 2000 + separator
                description = first + "다" * 2000
                pages = discord_sender.prepare_embeds([
                    discord_sender.make_embed("내용", description, "news")
                ])

                self.assertEqual(pages[0]["description"], first)
                self.assertEqual("".join(page["description"] for page in pages), description)

    def test_markdown_link_crossing_page_boundary_stays_clickable(self):
        link = "[긴 원문 링크](https://example.com/reports/" + "a" * 700 + "(2026))"
        description = "가" * 3700 + "\n" + link + "\n마감 확인"

        pages = discord_sender.prepare_embeds([
            discord_sender.make_embed("원문", description, "notice")
        ])

        self.assertEqual("".join(page["description"] for page in pages), description)
        self.assertTrue(any(link in page["description"] for page in pages))

    def test_word_boundary_inside_link_label_does_not_break_link(self):
        link = "[원문 자세히 보기](https://example.com/report)"
        description = link + "가" * 5000

        pages = discord_sender.prepare_embeds([
            discord_sender.make_embed("원문", description, "notice")
        ])

        self.assertIn(link, pages[0]["description"])
        self.assertEqual("".join(page["description"] for page in pages), description)

    def test_link_larger_than_a_page_preserves_all_text_without_hanging(self):
        description = "[원문](https://example.com/" + "a" * 9000 + ")"

        pages = discord_sender.prepare_embeds([
            discord_sender.make_embed("원문", description, "notice")
        ])

        self.assertEqual("".join(page["description"] for page in pages), description)
        self.assertTrue(all(0 < len(page["description"]) <= 4096 for page in pages))

    def test_long_unicode_pages_and_batches_fit_with_metadata(self):
        description = "🇰🇷🙂한글 " * 3000
        embed = discord_sender.make_embed("📰 공부 피드", description, "study")
        embed.update({
            "footer": {"text": "출처 확인 " * 200},
            "author": {"name": "Morning Brief"},
            "timestamp": "2026-09-13T07:00:00+09:00",
            "fields": [{"name": "기준", "value": "가" * 1000}],
        })
        before = deepcopy(embed)

        pages = discord_sender.prepare_embeds(iter([embed]))
        batches = discord_sender._batch_embeds(pages)

        self.assertEqual(embed, before)
        self.assertEqual("".join(page["description"] for page in pages), description)
        self.assertEqual(discord_sender.prepare_embeds(pages), pages)
        for page in pages:
            self.assertEqual(page["footer"], embed["footer"])
            self.assertEqual(page["timestamp"], embed["timestamp"])
            self.assertEqual(page["color"], embed["color"])
            self.assertLessEqual(discord_sender._text_length(page["description"]), 4096)
            self.assertLessEqual(discord_sender._text_length(page["title"]), 256)
        for batch in batches:
            self.assertLessEqual(len(batch), 10)
            self.assertLessEqual(sum(discord_sender._embed_char_count(page) for page in batch), 6000)
        pages[0]["footer"]["text"] = "changed"
        pages[0]["fields"][0]["value"] = "changed"
        self.assertEqual(embed, before)
        self.assertEqual(pages[1]["footer"], before["footer"])
        self.assertEqual(pages[1]["fields"], before["fields"])

    def test_page_suffix_respects_full_length_unicode_title(self):
        embed = discord_sender.make_embed("😀" * 128, "x" * 50000, "news")

        pages = discord_sender.prepare_embeds([embed])

        self.assertGreaterEqual(len(pages), 10)
        for index, page in enumerate(pages, 1):
            self.assertLessEqual(discord_sender._text_length(page["title"]), 256)
            self.assertTrue(page["title"].endswith(f" · {index}/{len(pages)}"))

    def test_unsplit_embeds_are_copied_and_keep_their_original_title(self):
        embed = {"title": "제목", "description": "내용", "footer": {"text": "출처"}}

        prepared = discord_sender.prepare_embeds([embed])

        self.assertEqual(prepared, [embed])
        self.assertIsNot(prepared[0], embed)
        self.assertIsNot(prepared[0]["footer"], embed["footer"])

    def test_invalid_metadata_fails_before_webhook_request(self):
        embed = discord_sender.make_embed("제목", "내용", "header")
        embed["footer"] = {"text": "x" * 2049}
        with mock.patch.object(discord_sender.urllib.request, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "footer.text"):
                discord_sender.send([embed])

        urlopen.assert_not_called()

    def test_same_url_pages_are_not_hidden_by_discord_deduplication(self):
        embeds = [
            {"title": str(index), "description": "내용", "url": "https://example.com/report"}
            for index in range(2)
        ]

        batches = discord_sender._batch_embeds(embeds)

        self.assertEqual([len(batch) for batch in batches], [1, 1])

    def test_send_and_dry_run_use_the_same_prepared_pages(self):
        embed = discord_sender.make_embed("공지", "공지\n" * 3000, "notice")
        expected = discord_sender.prepare_embeds([embed])
        with (
            mock.patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.invalid"}, clear=True),
            mock.patch.object(discord_sender.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen,
        ):
            discord_sender.send([embed])
        sent = [
            page
            for call in urlopen.call_args_list
            for page in json.loads(call.args[0].data)["embeds"]
        ]
        self.assertEqual(sent, expected)
        self.assertTrue(all(
            json.loads(call.args[0].data)["allowed_mentions"] == {"parse": []}
            for call in urlopen.call_args_list
        ))
        with (
            mock.patch.dict(os.environ, {"DISCORD_DRY_RUN": "1"}, clear=True),
            mock.patch.object(discord_sender, "_print_dry_run") as print_dry_run,
        ):
            discord_sender.send([embed])

        print_dry_run.assert_called_once_with(expected)

    def test_429_uses_retry_after_then_succeeds(self):
        rate_limit = http_error(429, '{"retry_after": 0.25}')
        with (
            mock.patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.invalid"}, clear=True),
            mock.patch.object(
                discord_sender.urllib.request,
                "urlopen",
                side_effect=[rate_limit, FakeResponse()],
            ) as urlopen,
            mock.patch.object(discord_sender.time, "sleep") as sleep,
        ):
            discord_sender.send([discord_sender.make_embed("제목", "내용", "header")])

        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_5xx_retries_with_backoff_then_succeeds(self):
        server_error = http_error(503)
        with (
            mock.patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.invalid"}, clear=True),
            mock.patch.object(
                discord_sender.urllib.request,
                "urlopen",
                side_effect=[server_error, FakeResponse()],
            ) as urlopen,
            mock.patch.object(discord_sender.time, "sleep") as sleep,
        ):
            discord_sender.send([discord_sender.make_embed("제목", "내용", "header")])

        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(discord_sender.RETRY_BASE_SECONDS)

    def test_non_retryable_http_error_fails_immediately(self):
        bad_request = http_error(400, '{"message": "bad payload"}')
        with (
            mock.patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.invalid"}, clear=True),
            mock.patch.object(
                discord_sender.urllib.request,
                "urlopen",
                side_effect=bad_request,
            ) as urlopen,
            mock.patch.object(discord_sender.time, "sleep") as sleep,
        ):
            with self.assertRaises(SystemExit):
                discord_sender.send([discord_sender.make_embed("제목", "내용", "header")])

        urlopen.assert_called_once()
        sleep.assert_not_called()

    def test_webhook_token_is_not_printed_from_transport_exception(self):
        marker = "PRIVATE-WEBHOOK-TOKEN"
        error = http.client.InvalidURL(f"bad /api/webhooks/123/{marker} path")
        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_WEBHOOK_URL": f"https://discord.com/api/webhooks/123/{marker} bad"},
                clear=True,
            ),
            mock.patch.object(discord_sender.urllib.request, "urlopen", side_effect=error),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            with self.assertRaises(SystemExit):
                discord_sender.send([discord_sender.make_embed("제목", "내용", "header")])

        self.assertNotIn(marker, stdout.getvalue())
        self.assertIn("InvalidURL", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
