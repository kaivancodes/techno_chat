import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from docx import Document as DocxDocument
from pptx import Presentation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from .ai_assistant_service import build_ai_assistant_prompt
from .chat_service import EMPTY_RAG_RESPONSE, GREETING_RESPONSE, build_chat_prompt
from .constants import CHAT_MODE_IMAGE_GENERATION
from .conversation_state_service import LAST_CHAT_KEY, get_conversation_state, update_conversation_state
from .image_generation_service import build_image_generation_prompt
from .helpers import attach_user_file_display_ids
from .models import ChatMessage, ChatSession, File, User
from .query_service import (
    build_query_variations,
    is_exact_request,
    resolve_vague_query,
    split_multi_question,
    should_refuse_for_abuse,
)
from .retrieval_service import retrieve_query_variations
from .structured_file_service import try_build_structured_answer
from .web_search_service import build_web_search_prompt


class QueryServiceTests(SimpleTestCase):
    def test_build_query_variations_expands_abbreviations_and_short_query(self):
        variations = build_query_variations("AI")
        self.assertEqual(variations[0], "AI")
        self.assertIn("artificial intelligence", variations[1].lower())
        self.assertEqual(len(variations), 3)

    def test_resolve_vague_query_uses_history_topic(self):
        chat_history = [SimpleNamespace(question="What are heart conditions?", answer="...")]
        resolved = resolve_vague_query("What are its symptoms?", chat_history=chat_history)
        self.assertIn("What are heart conditions", resolved)

    def test_resolve_vague_query_does_not_rewrite_this_file_phrase(self):
        chat_history = [SimpleNamespace(question="Tell me about cricket", answer="...")]
        resolved = resolve_vague_query("Give me the Indian players in this file", chat_history=chat_history)
        self.assertEqual(resolved, "Give me the Indian players in this file")

    def test_resolve_vague_query_anchors_short_definition_to_active_topic(self):
        resolved = resolve_vague_query("What is economy?", active_topic="cricket batting and bowling stats")
        self.assertIn("context of cricket batting and bowling stats", resolved)

    def test_resolve_vague_query_does_not_anchor_named_player_lookup(self):
        resolved = resolve_vague_query("Tell me about Joe Root.", active_topic="economy")
        self.assertEqual(resolved, "Tell me about Joe Root.")

    def test_exact_and_abuse_detection(self):
        self.assertTrue(is_exact_request("give the exact words"))
        self.assertTrue(should_refuse_for_abuse("you idiot"))
        self.assertFalse(should_refuse_for_abuse("what is AI idiot"))

    def test_split_multi_question_breaks_shared_metric_query_by_entity(self):
        parts = split_multi_question("What is the batting average of Virat Kohli, Kane Williamson, Steve Smith, and Joe Root?")
        self.assertEqual(parts, [
            "What is the batting average of Virat Kohli",
            "What is the batting average of Kane Williamson",
            "What is the batting average of Steve Smith",
            "What is the batting average of Joe Root",
        ])

    def test_split_multi_question_breaks_secondary_wh_question(self):
        parts = split_multi_question("What is the gap between a World Cup and when was the first played?")
        self.assertEqual(parts, [
            "What is the gap between a World Cup",
            "when was the first played",
        ])

    def test_split_multi_question_keeps_comparative_how_much_together(self):
        parts = split_multi_question("Which player has the lowest bowling average and how much?")
        self.assertEqual(parts, ["Which player has the lowest bowling average and how much?"])


class ConversationStateTests(SimpleTestCase):
    def test_conversation_state_keeps_broader_topic_across_entity_question(self):
        class DummySession(dict):
            modified = False

        request = SimpleNamespace(session=DummySession())

        update_conversation_state(
            request,
            session_id=1,
            query="Who has the best bowling average in ODI cricket?",
            resolved_query="Who has the best bowling average in ODI cricket?",
        )
        update_conversation_state(
            request,
            session_id=1,
            query="Tell me about David Warner.",
            resolved_query="Tell me about David Warner.",
        )

        state = get_conversation_state(request, 1)
        self.assertEqual(state["active_topic"], "cricket statistics and player performance")
        self.assertIn("David Warner", state["active_entities"])


class ChatServiceTests(SimpleTestCase):
    databases = {"default"}

    @patch("backoffice_engine.chat_service.retrieve_query_variations", return_value=[])
    def test_chat_prompt_uses_strict_empty_fallback(self, _mock_retrieve):
        result = build_chat_prompt("AI", [1], [], "Gemini 2.5 Flash")
        self.assertEqual(result["answer"], EMPTY_RAG_RESPONSE)

    def test_chat_prompt_greeting_only_on_first_message(self):
        result = build_chat_prompt("Hi", [1], [], "Gemini 2.5 Flash")
        self.assertEqual(result["answer"], GREETING_RESPONSE)

    @patch("backoffice_engine.chat_service.retrieve_query_variations")
    def test_exact_mode_returns_chunk_text_without_llm_rewrite(self, mock_retrieve):
        mock_retrieve.return_value = [{
            "text": "Exact definition from the document.",
            "score": 0.9,
            "file_id": 1,
            "chunk_index": 0,
            "file_name": "doc.pdf",
            "file_type": "pdf",
            "page_index": 2,
        }]
        result = build_chat_prompt("give exact words for definition", [1], [], "Gemini 2.5 Flash")
        self.assertEqual(result["answer"], "Exact definition from the document.")

    @patch("backoffice_engine.chat_service.retrieve_query_variations")
    @patch("backoffice_engine.chat_service._select_llm")
    @patch("backoffice_engine.chat_service.ChatPromptTemplate.from_messages")
    def test_chat_prompt_avoids_history_in_regular_rag_answers(self, mock_prompt_factory, _mock_select_llm, mock_retrieve):
        captured_payloads = []

        class FakeChain:
            def invoke(self, payload):
                captured_payloads.append(payload)
                return SimpleNamespace(content="Virat Kohli: 58.71")

        class FakePrompt:
            def __or__(self, _llm):
                return FakeChain()

        mock_prompt_factory.return_value = FakePrompt()
        mock_retrieve.return_value = [{
            "text": "Virat Kohli has an ODI batting average of 58.71.",
            "score": 0.95,
            "file_id": 1,
            "chunk_index": 0,
            "file_name": "doc.docx",
            "file_type": "docx",
            "page_index": 3,
        }]

        chat_history = [SimpleNamespace(question="Tell me about Pollard", answer="Pollard answer")]
        result = build_chat_prompt("What is the batting average of Virat Kohli?", [1], chat_history, "Gemini 2.5 Flash")

        self.assertEqual(result["answer"], "Virat Kohli: 58.71")
        self.assertEqual(captured_payloads[0]["chat_history"], [])

    @patch("backoffice_engine.chat_service.retrieve_query_variations")
    @patch("backoffice_engine.chat_service._select_llm")
    @patch("backoffice_engine.chat_service.ChatPromptTemplate.from_messages")
    def test_chat_prompt_uses_history_when_query_is_vague(self, mock_prompt_factory, _mock_select_llm, mock_retrieve):
        captured_payloads = []

        class FakeChain:
            def invoke(self, payload):
                captured_payloads.append(payload)
                return SimpleNamespace(content="Symptoms are listed in the document.")

        class FakePrompt:
            def __or__(self, _llm):
                return FakeChain()

        mock_prompt_factory.return_value = FakePrompt()
        mock_retrieve.return_value = [{
            "text": "Heart conditions symptoms include chest pain and fatigue.",
            "score": 0.91,
            "file_id": 1,
            "chunk_index": 0,
            "file_name": "doc.docx",
            "file_type": "docx",
            "page_index": 2,
        }]

        chat_history = [SimpleNamespace(question="What are heart conditions?", answer="...")]
        build_chat_prompt("What are its symptoms?", [1], chat_history, "Gemini 2.5 Flash")

        self.assertTrue(captured_payloads[0]["chat_history"])

    @patch("backoffice_engine.chat_service.retrieve_query_variations")
    def test_list_queries_request_broader_retrieval(self, mock_retrieve):
        mock_retrieve.return_value = []
        build_chat_prompt("Give me the name of the Indian players mentioned in this file. All 5.", [1], [], "Gemini 2.5 Flash")
        self.assertGreaterEqual(mock_retrieve.call_args.kwargs["max_chunks"], 12)

    @patch("backoffice_engine.chat_service.retrieve_query_variations")
    def test_sources_are_deduplicated_by_location(self, mock_retrieve):
        chunk = {
            "text": "Sachin Tendulkar played for India.",
            "score": 0.9,
            "file_id": 1,
            "chunk_index": 0,
            "file_name": "doc.docx",
            "file_type": "docx",
            "page_index": 2,
        }
        mock_retrieve.return_value = [chunk, dict(chunk)]
        result = build_chat_prompt("give exact words for Sachin Tendulkar", [1], [], "Gemini 2.5 Flash")
        self.assertEqual(len(result["sources"]), 1)

    @patch("backoffice_engine.chat_service.retrieve_query_variations")
    @patch("backoffice_engine.chat_service._select_llm")
    @patch("backoffice_engine.chat_service.ChatPromptTemplate.from_messages")
    def test_rag_uses_llm_selected_context_ids_for_sources(self, mock_prompt_factory, _mock_select_llm, mock_retrieve):
        class FakeChain:
            def invoke(self, payload):
                return SimpleNamespace(content='{"answer":"Sachin Tendulkar","used_context_ids":[2]}')

        class FakePrompt:
            def __or__(self, _llm):
                return FakeChain()

        mock_prompt_factory.return_value = FakePrompt()
        mock_retrieve.return_value = [
            {
                "text": "Virat Kohli scored many runs.",
                "score": 0.8,
                "file_id": 1,
                "chunk_index": 0,
                "file_name": "doc.docx",
                "file_type": "docx",
                "page_index": 2,
            },
            {
                "text": "Sachin Tendulkar is listed on this page.",
                "score": 0.9,
                "file_id": 1,
                "chunk_index": 1,
                "file_name": "doc.docx",
                "file_type": "docx",
                "page_index": 5,
            },
        ]

        result = build_chat_prompt("Who is mentioned?", [1], [], "Gemini 2.5 Flash")
        self.assertEqual(result["sources"][0]["page_index"], 5)


class RetrievalServiceTests(SimpleTestCase):
    @patch("backoffice_engine.retrieval_service.hybrid_search", return_value=[])
    def test_query_variations_use_single_hybrid_search_call(self, mock_hybrid_search):
        retrieve_query_variations(
            query_variations=["List all players", "List all players exact names only all matching items mentioned in the document"],
            file_ids=[1],
            max_chunks=12,
            token_budget=4000,
        )

        mock_hybrid_search.assert_called_once()

    @patch("backoffice_engine.retrieval_service.hybrid_search", return_value=[])
    def test_default_query_variations_do_not_expand_top_k_too_aggressively(self, mock_hybrid_search):
        retrieve_query_variations(
            query_variations=["Tell me about Joe Root."],
            file_ids=[1],
            max_chunks=8,
            token_budget=2800,
        )

        self.assertEqual(mock_hybrid_search.call_args.kwargs["top_k"], 12)
        self.assertEqual(mock_hybrid_search.call_args.kwargs["top_n"], 8)


class AssistantAndWebServiceTests(SimpleTestCase):
    @patch("backoffice_engine.ai_assistant_service._select_llm")
    @patch("backoffice_engine.ai_assistant_service.ChatPromptTemplate.from_messages")
    def test_ai_assistant_refactors_multi_question(self, mock_prompt_factory, _mock_select_llm):
        captured_inputs = []

        class FakeChain:
            def invoke(self, payload):
                captured_inputs.append(payload["input"])
                return SimpleNamespace(content='{"answer":"done"}')

        class FakePrompt:
            def __or__(self, _llm):
                return FakeChain()

        mock_prompt_factory.return_value = FakePrompt()
        build_ai_assistant_prompt(
            "What is the gap between a World Cup and when was the first played?",
            chat_history=[],
            model_name="Gemini 2.5 Flash",
            conversation_state={},
        )

        self.assertEqual(captured_inputs, [
            "What is the gap between Cricket World Cups",
            "when was the first played",
        ])

    @patch("backoffice_engine.web_search_service._select_llm")
    @patch("backoffice_engine.web_search_service.SerperClient")
    def test_web_search_uses_only_llm_selected_sources(self, mock_serper_cls, mock_select_llm):
        mock_serper_cls.return_value.search.return_value = [
            {"title": "One", "link": "https://a.example", "snippet": "first"},
            {"title": "Two", "link": "https://b.example", "snippet": "second"},
        ]

        class FakeLLM:
            def invoke(self, _messages):
                return SimpleNamespace(content='{"answer":"final","used_result_ids":[2]}')

        mock_select_llm.return_value = FakeLLM()
        result = build_web_search_prompt(
            "Latest cricket world cup",
            model_name="Gemini 2.5 Flash",
            chat_history=[],
            conversation_state={},
        )

        self.assertEqual(result["sources"], [{"title": "Two", "link": "https://b.example"}])

    @patch("backoffice_engine.ai_assistant_service._select_llm")
    @patch("backoffice_engine.ai_assistant_service.ChatPromptTemplate.from_messages")
    def test_ai_assistant_strips_fenced_json_answer(self, mock_prompt_factory, _mock_select_llm):
        class FakeChain:
            def invoke(self, payload):
                return SimpleNamespace(content='```json\n{"answer":"Virat Kohli is a batter."}\n```')

        class FakePrompt:
            def __or__(self, _llm):
                return FakeChain()

        mock_prompt_factory.return_value = FakePrompt()
        result = build_ai_assistant_prompt(
            "Who is Virat Kohli?",
            chat_history=[],
            model_name="Gemini 2.5 Flash",
            conversation_state={},
        )

        self.assertEqual(result["answer"], "Virat Kohli is a batter.")

    @patch("backoffice_engine.web_search_service._select_llm")
    @patch("backoffice_engine.web_search_service.SerperClient")
    def test_web_search_strips_fenced_json_answer(self, mock_serper_cls, mock_select_llm):
        mock_serper_cls.return_value.search.return_value = [
            {"title": "One", "link": "https://a.example", "snippet": "first"},
        ]

        class FakeLLM:
            def invoke(self, _messages):
                return SimpleNamespace(content='```json\n{"answer":"final","used_result_ids":[1]}\n```')

        mock_select_llm.return_value = FakeLLM()
        result = build_web_search_prompt(
            "Latest cricket world cup",
            model_name="Gemini 2.5 Flash",
            chat_history=[],
            conversation_state={},
        )

        self.assertEqual(result["answer"], "final")
        self.assertEqual(result["sources"], [{"title": "One", "link": "https://a.example"}])


class StructuredFileServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="structured@technostacks.com", password="secret")
        self.file = File.objects.create(
            user=self.user,
            file_type="txt",
            file=SimpleUploadedFile("cricket.txt", (
                b"Batting Average\n"
                b"Runs divided by dismissals.\n\n"
                b"India\n"
                b"MS Dhoni\n"
                b"Mahendra Singh Dhoni, India\xe2\x80\x99s most successful ODI captain, scored 10,773 runs.\n"
                b"Virat Kohli\n"
                b"Virat Kohli is the modern giant of ODI cricket and scored 13,797 runs.\n"
                b"Jasprit Bumrah\n"
                b"Jasprit Bumrah, India\xe2\x80\x99s premier fast bowler, has taken 149 wickets.\n"
                b"Sri Lanka\n"
                b"Kumar Sangakkara\n"
                b"Kumar Sangakkara, Sri Lanka\xe2\x80\x99s elegant left handed batsman and wicketkeeper, scored 14,234 runs.\n"
            )),
            original_filename="cricket.txt",
        )

    def test_structured_service_answers_player_lookup(self):
        result = try_build_structured_answer("Who is Virat Kohli?", [self.file.id])
        self.assertIsNotNone(result)
        self.assertIn("Virat Kohli", result["answer"])
        self.assertIn("13,797 runs", result["answer"])
        self.assertNotEqual(result["answer"], "Virat Kohli is the modern giant of ODI cricket and scored 13,797 runs.")
        self.assertEqual(result["sources"][0]["line_start"], 7)

    def test_structured_service_answers_country_list(self):
        result = try_build_structured_answer("List the Indian cricketers only names", [self.file.id])
        self.assertEqual(result["answer"], "MS Dhoni\nVirat Kohli\nJasprit Bumrah")

    def test_structured_service_answers_summary(self):
        result = try_build_structured_answer("Give me summary", [self.file.id])
        self.assertIn("4 cricketers", result["answer"])
        self.assertIn("India: MS Dhoni, Virat Kohli, Jasprit Bumrah", result["answer"])

    def test_structured_service_answers_glossary_definition(self):
        result = try_build_structured_answer("What is batting average?", [self.file.id])
        self.assertEqual(result["answer"], "Runs divided by dismissals.")

    def test_structured_service_matches_cricket_glossary_alias(self):
        economy_file = File.objects.create(
            user=self.user,
            file_type="txt",
            file=SimpleUploadedFile("economy.txt", (
                b"Economy Rate (Econ)\n"
                b"Runs given per over.\n\n"
                b"India\n"
                b"MS Dhoni\n"
                b"Mahendra Singh Dhoni scored 10,773 runs.\n"
            )),
            original_filename="economy.txt",
        )

        result = try_build_structured_answer("What is economy?", [economy_file.id])
        self.assertIsNotNone(result)
        self.assertEqual(result["answer"], "Runs given per over.")

    @patch("backoffice_engine.chat_service.retrieve_query_variations", return_value=[])
    def test_chat_service_uses_structured_answer_when_available(self, _mock_retrieve):
        result = build_chat_prompt("Who is Virat Kohli?", [self.file.id], [], "Gemini 2.5 Flash")
        self.assertIn("Virat Kohli", result["answer"])
        self.assertIn("13,797 runs", result["answer"])
        self.assertEqual(len(result["sources"]), 1)

    @patch("backoffice_engine.chat_service.retrieve_query_variations")
    @patch("backoffice_engine.chat_service.try_build_structured_answer")
    def test_chat_service_skips_retrieval_when_structured_answer_exists(self, mock_structured, mock_retrieve):
        mock_structured.return_value = {
            "answer": "AB de Villiers stats",
            "sources": [{"file_id": self.file.id, "file_name": "cricket.txt", "file_type": "txt", "line_start": 1, "line_end": 2}],
        }

        result = build_chat_prompt("Give me full stat of AB de Villiers", [self.file.id], [], "Gemini 2.5 Flash")

        self.assertEqual(result["answer"], "AB de Villiers stats")
        mock_retrieve.assert_not_called()


class RealCricketFileStructuredTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="realcricket@technostacks.com", password="secret")
        txt_content = Path("test_media/files/ODI_Cricket_Country.txt").read_bytes()
        md_content = Path("test_media/files/ODI_Cricket_Stats.md").read_bytes()
        self.txt_file = File.objects.create(
            user=self.user,
            file_type="txt",
            file=SimpleUploadedFile("ODI_Cricket_Country.txt", txt_content),
            original_filename="ODI_Cricket_Country.txt",
        )
        self.md_file = File.objects.create(
            user=self.user,
            file_type="md",
            file=SimpleUploadedFile("ODI_Cricket_Stats.md", md_content),
            original_filename="ODI_Cricket_Stats.md",
        )

    def test_real_file_player_count(self):
        result = try_build_structured_answer("How many cricket players are mentioned in the file?", [self.txt_file.id])
        self.assertEqual(result["answer"], "35 cricket players are mentioned in the file.")

    def test_real_file_country_count(self):
        result = try_build_structured_answer("How many countries are mentioned in the file?", [self.txt_file.id])
        self.assertEqual(result["answer"], "7")

    def test_real_file_country_list_includes_india(self):
        result = try_build_structured_answer("Name the countries mentioned in the file.", [self.txt_file.id])
        self.assertIn("India", result["answer"])
        self.assertIn("South Africa", result["answer"])
        self.assertIn("West Indies", result["answer"])

    def test_real_markdown_country_list_includes_india(self):
        result = try_build_structured_answer("Name the countries mentioned", [self.md_file.id])
        self.assertIn("India", result["answer"])
        self.assertIn("Australia", result["answer"])
        self.assertIn("England", result["answer"])

    def test_real_file_west_indies_players(self):
        result = try_build_structured_answer("List the West Indies players", [self.txt_file.id])
        self.assertEqual(
            result["answer"],
            "Kieron Pollard\nDwayne Bravo\nChris Gayle\nSunil Narine\nJason Holder",
        )

    def test_real_file_proteas_players(self):
        result = try_build_structured_answer("Name the Proteas players", [self.txt_file.id])
        self.assertEqual(
            result["answer"],
            "Hashim Amla\nAB de Villiers\nJacques Kallis\nShaun Pollock\nDale Steyn",
        )

    def test_real_file_highest_sixes(self):
        result = try_build_structured_answer("Highest sixes amongst the players mentioned in the file?", [self.txt_file.id])
        self.assertEqual(result["answer"], "Chris Gayle has the highest sixes with 331 sixes.")

    def test_real_file_highest_runouts_reports_tie(self):
        result = try_build_structured_answer("Amongst the players mentioned who has got highest runouts?", [self.txt_file.id])
        self.assertIn("MS Dhoni", result["answer"])
        self.assertIn("Kumar Sangakkara", result["answer"])
        self.assertIn("highest runouts", result["answer"])
        self.assertIn("35 runouts each", result["answer"])

    def test_real_file_best_batting_average_returns_player_and_value(self):
        result = try_build_structured_answer("Best average?", [self.md_file.id])
        self.assertIn("Virat Kohli", result["answer"])
        self.assertIn("58.71", result["answer"])

    def test_real_file_lowest_bowling_average_returns_player_and_value(self):
        result = try_build_structured_answer("Which player has the lowest bowling average and how much?", [self.md_file.id])
        self.assertIsNotNone(result)
        self.assertIn("Mitchell Starc", result["answer"])
        self.assertIn("22", result["answer"])

    def test_real_file_player_specific_stat(self):
        result = try_build_structured_answer("MS Dhoni sixes count.", [self.md_file.id])
        self.assertEqual(result["answer"], "MS Dhoni: 229 sixes")

    def test_real_file_multi_player_selected_fields(self):
        result = try_build_structured_answer(
            "Give Runs, batting average, and strike rate of MS Dhoni, Brendon McCullum, Kumar Sangakkara, AB DeVilliers.",
            [self.md_file.id],
        )
        self.assertIn("MS Dhoni — Runs: 10,773, Batting Average: 50.57, Strike Rate: 87.56", result["answer"])
        self.assertIn("Brendon McCullum — Runs: 6,083, Batting Average: 30.41, Strike Rate: 96.37", result["answer"])
        self.assertIn("Kumar Sangakkara — Runs: 14,234, Batting Average: 41.98, Strike Rate: 78.86", result["answer"])
        self.assertIn("AB de Villiers — Runs: 9,577, Batting Average: 53.5, Strike Rate: 101.09", result["answer"])


class ViewBehaviorTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create(email="user1@technostacks.com", password="secret")
        session = self.client.session
        session["user_id"] = self.user.id
        session.save()

    def test_chat_list_preserves_last_active_session(self):
        first = ChatSession.objects.create(user=self.user, title="Chat 1")
        second = ChatSession.objects.create(user=self.user, title="Chat 2")
        session = self.client.session
        session[LAST_CHAT_KEY] = second.id
        session.save()

        response = self.client.get(reverse("chat_list"))
        self.assertRedirects(response, reverse("chat", args=[second.id]))
        self.assertNotEqual(first.id, second.id)

    def test_chat_send_uses_only_last_five_messages(self):
        chat_session = ChatSession.objects.create(user=self.user, title="History")
        for index in range(6):
            ChatMessage.objects.create(
                session=chat_session,
                question=f"Question {index}",
                answer=f"Answer {index}",
                model_used="Gemini 2.5 Flash",
                chat_mode="ai_assistant",
            )

        with patch("backoffice_engine.views.build_ai_assistant_prompt") as mock_builder:
            mock_builder.return_value = {
                "answer": "Done",
                "sources": [],
                "is_greeting": False,
                "is_summary": False,
                "chat_mode": "ai_assistant",
                "resolved_query": "Done",
            }

            response = self.client.post(
                reverse("chat_send", args=[chat_session.id]),
                data='{"query":"follow up","model_name":"Gemini 2.5 Flash","chat_mode":"ai_assistant"}',
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mock_builder.call_args.kwargs["chat_history"]), 5)

    def test_file_display_ids_restart_per_user(self):
        other_user = User.objects.create(email="user2@technostacks.com", password="secret")
        File.objects.create(user=self.user, file_type="pdf", file=SimpleUploadedFile("a.pdf", b"1"), original_filename="a.pdf")
        File.objects.create(user=self.user, file_type="pdf", file=SimpleUploadedFile("b.pdf", b"1"), original_filename="b.pdf")
        user_two_files = [
            File.objects.create(user=other_user, file_type="pdf", file=SimpleUploadedFile("c.pdf", b"1"), original_filename="c.pdf"),
            File.objects.create(user=other_user, file_type="pdf", file=SimpleUploadedFile("d.pdf", b"1"), original_filename="d.pdf"),
        ]

        decorated = list(attach_user_file_display_ids(File.objects.filter(user=other_user).order_by("-created_at")))
        self.assertEqual([item.display_file_id for item in decorated], [2, 1])
        self.assertEqual(len(user_two_files), 2)

    def test_multipart_image_request_routes_to_generation_service(self):
        chat_session = ChatSession.objects.create(user=self.user, title="Images")
        with patch("backoffice_engine.views.build_image_generation_prompt") as mock_builder:
            mock_builder.return_value = {
                "answer": "Here is the edited image.",
                "sources": [{"kind": "generated_image", "image_url": "https://example.com/image.png"}],
                "is_greeting": False,
                "is_summary": False,
                "chat_mode": CHAT_MODE_IMAGE_GENERATION,
                "image_urls": ["https://example.com/image.png"],
                "selected_model": "seedream-model",
                "resolved_query": "edit image",
            }

            response = self.client.post(
                reverse("chat_send", args=[chat_session.id]),
                data={
                    "query": "edit image",
                    "model_name": "Gemini 2.5 Flash",
                    "chat_mode": CHAT_MODE_IMAGE_GENERATION,
                    "image": SimpleUploadedFile("edit.png", b"123", content_type="image/png"),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"]["chat_mode"], CHAT_MODE_IMAGE_GENERATION)

    def test_upload_image_requires_image_mode(self):
        chat_session = ChatSession.objects.create(user=self.user, title="Images")
        response = self.client.post(
            reverse("chat_send", args=[chat_session.id]),
            data={
                "query": "edit image",
                "model_name": "Gemini 2.5 Flash",
                "chat_mode": "rag",
                "image": SimpleUploadedFile("edit.png", b"123", content_type="image/png"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Select Create Image mode", response.json()["error"])

    def test_page_render_falls_back_to_text_when_original_file_is_missing(self):
        uploaded = SimpleUploadedFile("missing.pdf", b"%PDF-1.4 fake")
        file_obj = File.objects.create(
            user=self.user,
            file_type="pdf",
            file=uploaded,
            original_filename="missing.pdf",
        )
        stored_path = file_obj.file.path
        if os.path.exists(stored_path):
            os.remove(stored_path)

        response = self.client.get(reverse("page_render"), {
            "file_id": file_obj.id,
            "file_type": "pdf",
            "page_index": 1,
            "highlight": "Joe Root",
        })

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["source_type"], "text")
        self.assertIn("Requested source: page 1.", payload["content_text"])
        self.assertNotIn("Matched text:", payload["content_text"])

    def test_page_render_returns_visual_preview_for_docx(self):
        doc = DocxDocument()
        doc.add_paragraph("Virat Kohli is in the first page preview.")
        doc_stream = BytesIO()
        doc.save(doc_stream)
        doc_stream.seek(0)
        file_obj = File.objects.create(
            user=self.user,
            file_type="doc",
            file=SimpleUploadedFile("preview.docx", doc_stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            original_filename="preview.docx",
        )

        response = self.client.get(reverse("page_render"), {
            "file_id": file_obj.id,
            "file_type": "docx",
            "page_index": 1,
        })

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["source_type"], "page")
        self.assertIn("/media/page_renders/", payload["image_url"])

    def test_page_render_returns_visual_preview_for_pptx(self):
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "David Warner"
        slide.placeholders[1].text = "Aggressive opener for Australia."
        ppt_stream = BytesIO()
        presentation.save(ppt_stream)
        ppt_stream.seek(0)
        file_obj = File.objects.create(
            user=self.user,
            file_type="power",
            file=SimpleUploadedFile("preview.pptx", ppt_stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            original_filename="preview.pptx",
        )

        response = self.client.get(reverse("page_render"), {
            "file_id": file_obj.id,
            "file_type": "pptx",
            "slide_index": 1,
        })

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["source_type"], "page")
        self.assertIn("/media/page_renders/", payload["image_url"])

    def test_page_render_returns_original_image_for_image_source(self):
        image = Image.new("RGB", (40, 40), "red")
        image_stream = BytesIO()
        image.save(image_stream, format="PNG")
        image_stream.seek(0)
        file_obj = File.objects.create(
            user=self.user,
            file_type="image",
            file=SimpleUploadedFile("preview.png", image_stream.getvalue(), content_type="image/png"),
            original_filename="preview.png",
        )

        response = self.client.get(reverse("page_render"), {
            "file_id": file_obj.id,
            "file_type": "png",
            "page_index": 1,
        })

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["source_type"], "page")
        self.assertIn("/media/files/", payload["image_url"])

    @patch("backoffice_engine.image_generation_service.KieImageClient")
    def test_image_generation_uses_uploaded_image_data_uri(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.api_key = "key"
        mock_client.text_model = "4o-image-api"
        mock_client.edit_model = "4o-image-api"
        mock_client.image_to_image.return_value = ["https://example.com/out.png"]
        request = SimpleNamespace(build_absolute_uri=lambda path: f"http://localhost:8000{path}")
        uploaded = SimpleUploadedFile("edit.png", b"\x89PNG", content_type="image/png")

        result = build_image_generation_prompt("edit this image", request=request, uploaded_image=uploaded)

        image_inputs = mock_client.image_to_image.call_args.args[1]
        self.assertEqual(len(image_inputs), 1)
        self.assertTrue(image_inputs[0].startswith("data:image/png;base64,"))
        self.assertEqual(result["chat_mode"], CHAT_MODE_IMAGE_GENERATION)

    @patch("backoffice_engine.clients._requests.get")
    @patch("backoffice_engine.clients._requests.post")
    def test_kie_4o_client_uses_documented_endpoints(self, mock_post, mock_get):
        from .clients import KieImageClient

        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"data": {"taskId": "task123"}}
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "data": {
                "status": "SUCCESS",
                "response": {
                    "resultUrls": ["https://example.com/generated.png"],
                },
            },
        }

        client = KieImageClient(api_key="key")
        client.text_model = "4o-image-api"
        client.edit_model = "4o-image-api"
        urls = client.text_to_image("make a poster")

        self.assertEqual(urls, ["https://example.com/generated.png"])
        self.assertIn("/gpt4o-image/generate", mock_post.call_args.args[0])
        self.assertIn("/gpt4o-image/record-info", mock_get.call_args.args[0])

    @patch("backoffice_engine.clients._requests.get")
    @patch("backoffice_engine.clients._requests.post")
    def test_kie_4o_image_to_image_uploads_data_url_first(self, mock_post, mock_get):
        from .clients import KieImageClient

        upload_response = Mock()
        upload_response.raise_for_status.return_value = None
        upload_response.json.return_value = {"data": {"fileUrl": "https://files.example/input.png"}}

        generate_response = Mock()
        generate_response.raise_for_status.return_value = None
        generate_response.json.return_value = {"data": {"taskId": "task123"}}

        mock_post.side_effect = [upload_response, generate_response]

        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "data": {
                "status": "SUCCESS",
                "response": {
                    "resultUrls": ["https://example.com/generated.png"],
                },
            },
        }

        client = KieImageClient(api_key="key")
        client.edit_model = "4o-image-api"
        urls = client.image_to_image("edit this image", ["data:image/png;base64,AAAA"])

        self.assertEqual(urls, ["https://example.com/generated.png"])
        self.assertIn("/file-base64-upload", mock_post.call_args_list[0].args[0])
        self.assertEqual(
            mock_post.call_args_list[1].kwargs["json"]["filesUrl"],
            ["https://files.example/input.png"],
        )

    @patch("backoffice_engine.clients._requests.get")
    @patch("backoffice_engine.clients._requests.post")
    def test_kie_upload_accepts_string_data_payload(self, mock_post, mock_get):
        from .clients import KieImageClient

        upload_response = Mock()
        upload_response.raise_for_status.return_value = None
        upload_response.json.return_value = {"data": "https://files.example/input.png"}

        generate_response = Mock()
        generate_response.raise_for_status.return_value = None
        generate_response.json.return_value = {"data": {"taskId": "task123"}}
        mock_post.side_effect = [upload_response, generate_response]

        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "data": {
                "status": "SUCCESS",
                "response": {
                    "resultUrls": ["https://example.com/generated.png"],
                },
            },
        }

        client = KieImageClient(api_key="key")
        client.edit_model = "4o-image-api"
        urls = client.image_to_image("edit this image", ["data:image/png;base64,AAAA"])

        self.assertEqual(urls, ["https://example.com/generated.png"])
