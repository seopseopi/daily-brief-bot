import unittest
from unittest import mock

from sources import _discord


class DiscordSourceTests(unittest.TestCase):
    def test_history_pages_backwards_and_returns_chronological_unique_messages(self):
        newest = [{"id": str(value)} for value in range(101, 201)]
        older = [{"id": str(value)} for value in range(1, 101)]
        with mock.patch.object(
            _discord,
            "fetch_channel_messages",
            side_effect=[newest, older, []],
        ) as fetch:
            messages = _discord.fetch_channel_history("123", "token", max_messages=300)

        self.assertEqual([message["id"] for message in messages], [str(i) for i in range(1, 201)])
        self.assertIsNone(fetch.call_args_list[0].kwargs["before_id"])
        self.assertEqual(fetch.call_args_list[1].kwargs["before_id"], "101")
        self.assertEqual(fetch.call_args_list[2].kwargs["before_id"], "1")

    def test_history_limit_fails_instead_of_returning_possibly_incomplete_state(self):
        page = [{"id": str(value)} for value in range(1, 101)]
        with mock.patch.object(_discord, "fetch_channel_messages", return_value=page):
            with self.assertRaisesRegex(RuntimeError, "ASSIGNMENT_HISTORY_LIMIT"):
                _discord.fetch_channel_history("123", "token", max_messages=100)

    def test_invalid_channel_id_is_rejected_before_request(self):
        with self.assertRaisesRegex(ValueError, "numeric"):
            _discord.fetch_channel_messages("not-a-channel", "token")


if __name__ == "__main__":
    unittest.main()
