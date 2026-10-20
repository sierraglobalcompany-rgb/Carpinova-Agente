"""Topic evidence screening tests — lexical only, never technical certification."""
import copy
import unittest

from knowledge_client.reader import BundleError
from knowledge_client.topic_screen import TOPIC_TERMS, screen_topic_results


def record(identifier, text, tags=(), page=110):
    return {
        "content_id": identifier, "page_id": f"PAGE-{page}",
        "pdf_page": page, "printed_page": page-22,
        "review_status": "VISUALLY_VERIFIED", "text": text,
        "tags": list(tags), "source_book": "cpnc-2025",
        "manufacturing_authority": False,
    }


def sample(*items):
    return {"query": "fondo y tuberías", "coverage": "PARTIAL_CORPUS",
            "knowledge_version": "1.2.0", "results": list(items),
            "total_matches": 98, "source_pdf_bytes_verified": False,
            "technical_use": "REFERENCE_ONLY_NOT_FABRICATION_AUTHORITY"}


class TopicScreenTests(unittest.TestCase):
    def test_all_declared_topics_have_context(self):
        self.assertEqual(set(TOPIC_TERMS), {
            "edge_banding", "backs_and_services", "screws_and_connectors",
            "wall_support", "floor_support",
        })

    def test_back_and_services_must_share_one_record(self):
        a=record("BACK", "El fondo tiene recubrimiento.",page=110)
        b=record("PIPE", "Revisar tuberías de la cocina.",page=111)
        out=screen_topic_results(sample(a,b), "backs_and_services")
        self.assertEqual(out["results"], [])
        self.assertEqual(out["relevance_review"]["candidate_count_in_sample"],0)
        self.assertEqual(out["relevance_review"]["status"],
                         "NO_CONTEXT_CANDIDATES_IN_SEARCH_SAMPLE")
        self.assertEqual(out["total_matches"],98)

    def test_contextual_candidate_is_not_technical_rule(self):
        item=record("SERVICE", "Fondo registrable para acceso a tuberías.",page=134)
        base=sample(item)
        out=screen_topic_results(base,"backs_and_services")
        self.assertEqual(out["results"][0],item)
        self.assertEqual(out["results"][0]["pdf_page"],134)
        self.assertEqual(out["results"][0]["printed_page"],112)
        self.assertEqual(out["relevance_review"]["records"][0]["relation_status"],
                         "TEXT_CONTEXT_CANDIDATE")
        self.assertFalse(out["relevance_review"]["technical_suitability_verified"])
        self.assertFalse(out["relevance_review"]["reviewed_against_original_pdf"])
        self.assertFalse(out["relevance_review"]["manufacturer_spec_verified"])
        self.assertFalse(out["relevance_review"]["records"][0]["technical_rule_verified"])
        self.assertEqual(base["results"],[item])

    def test_no_false_substring_encanto_for_canto(self):
        x=sample(record("ENCANTO","Qué encanto de muebles.",page=123))
        o=screen_topic_results(x,"edge_banding")
        self.assertEqual(o["results"],[])

    def test_accents_and_plural_words(self):
        x=sample(record("EDGE","Los tapacantos protegen bordes.",page=123))
        self.assertEqual(len(screen_topic_results(x,"edge_banding")["results"]),1)
        y=sample(record("SUPPORT","Anclajes en pared de concreto.",page=120))
        self.assertEqual(len(screen_topic_results(y,"wall_support")["results"]),1)

    def test_wall_support_requires_wall_and_anchor(self):
        x=sample(record("WALL","La pared está enchapada."),
                 record("ANCHOR","El anclaje soporta el módulo."))
        self.assertEqual(screen_topic_results(x,"wall_support")["results"],[])

    def test_tags_only_is_explicitly_weaker_signal(self):
        item=record("TAGGED","Se debe revisar este texto.",
                    ["cantos"],page=131)
        o=screen_topic_results(sample(item),"edge_banding")
        self.assertEqual(o["relevance_review"]["records"][0]["relation_status"],
                         "TEXT_AND_TAG_CANDIDATE")
        self.assertTrue(o["relevance_review"]["candidate_count_in_sample"])
        self.assertFalse(o["relevance_review"]["reviewed_against_original_pdf"])

    def test_direct_text_has_priority_over_editorial_tags(self):
        tagged=record("TAG","Texto genérico.",["cantos"],page=101)
        direct=record("TEXT","El canto cubre el tablero.",page=210)
        o=screen_topic_results(sample(tagged,direct),"edge_banding")
        self.assertEqual([x["content_id"] for x in o["results"]],["TEXT","TAG"])

    def test_fasteners_and_floor_support(self):
        a=record("SCREW","Un tornillo requiere fijación.",page=80)
        b=record("FLOOR","Patas niveladoras y zócalo.",page=90)
        self.assertEqual([r["content_id"] for r in screen_topic_results(
            sample(a,b),"screws_and_connectors")["results"]],["SCREW"])
        self.assertEqual([r["content_id"] for r in screen_topic_results(
            sample(a,b),"floor_support")["results"]],["FLOOR"])

    def test_invalid_topic_or_result_shape_fail_closed(self):
        with self.assertRaises(BundleError):
            screen_topic_results(sample(),"made_up")
        with self.assertRaises(BundleError):
            screen_topic_results(sample(),None)
        with self.assertRaises(BundleError):
            screen_topic_results({"results":{}}, "edge_banding")
        with self.assertRaises(BundleError):
            screen_topic_results(sample({"content_id":None}),"edge_banding")

    def test_large_window_returns_only_five_references(self):
        items=[record(f"EDGE-{i}","Cantos en tableros.",page=70+i)
               for i in range(16)]
        outcome=screen_topic_results(sample(*items),"edge_banding")
        self.assertEqual(len(outcome["results"]),5)
        self.assertEqual(outcome["relevance_review"]["candidate_count_in_sample"],16)
        self.assertEqual(outcome["relevance_review"]["returned_candidate_count"],5)
        self.assertEqual(outcome["relevance_review"]["sampled_result_count"],16)
        self.assertEqual(outcome["total_matches"],98)

    def test_source_record_is_not_mutated(self):
        base=sample(record("A","Fondo detrás de tubería."),
                    record("B","Tornillos y escuadras."))
        before=copy.deepcopy(base)
        screen_topic_results(base,"backs_and_services")
        self.assertEqual(base,before)
        self.assertEqual(base["results"][0]["review_status"],"VISUALLY_VERIFIED")


if __name__=="__main__":
    unittest.main()
