"""Run a small local RAG prompt and retrieval evaluation.

Requires the same Pinecone/Groq configuration as the app. Results are written
to evaluation_results.json and evaluation_summary.md in the project root.
The retrieval hit@3 label is operationalized as: a top-three chunk contains at
least one query-specific expected phrase. Review labels before using scores as
formal relevance judgments.
"""
import json
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_pinecone import PineconeVectorStore

from src.helper import download_hugging_face_embeddings
from src.prompt import PROMPT_VARIANTS


QUESTIONS = [
    ("What is hypertension?", ["high blood pressure", "blood pressure"]),
    ("What are common symptoms of diabetes?", ["diabetes", "blood glucose"]),
    ("What is hypoglycemia?", ["low blood sugar", "blood glucose"]),
    ("What is anemia?", ["anemia", "hemoglobin"]),
    ("What causes iron deficiency anemia?", ["iron deficiency", "iron"]),
    ("What is asthma?", ["asthma", "airway"]),
    ("What are symptoms of pneumonia?", ["pneumonia", "lung"]),
    ("What is tuberculosis?", ["tuberculosis", "tubercle bacillus"]),
    ("How does influenza spread?", ["influenza", "virus"]),
    ("What is dehydration?", ["dehydration", "fluid"]),
    ("What is a migraine?", ["migraine", "headache"]),
    ("What is epilepsy?", ["epilepsy", "seizure"]),
    ("What is a stroke?", ["stroke", "cerebral"]),
    ("What is coronary artery disease?", ["coronary", "artery"]),
    ("What is heart failure?", ["heart failure", "cardiac"]),
    ("What is hepatitis?", ["hepatitis", "liver"]),
    ("What is cirrhosis?", ["cirrhosis", "liver"]),
    ("What is a peptic ulcer?", ["ulcer", "stomach"]),
    ("What is gastroenteritis?", ["gastroenteritis", "intestinal"]),
    ("What is a urinary tract infection?", ["urinary tract", "infection"]),
    ("What is a kidney stone?", ["kidney stone", "renal calculus"]),
    ("What is hypothyroidism?", ["hypothyroidism", "thyroid"]),
    ("What is hyperthyroidism?", ["hyperthyroidism", "thyroid"]),
    ("What is osteoporosis?", ["osteoporosis", "bone"]),
    ("What is rheumatoid arthritis?", ["rheumatoid arthritis", "joint"]),
    ("What is eczema?", ["eczema", "skin"]),
    ("What is psoriasis?", ["psoriasis", "skin"]),
    ("What is sepsis?", ["sepsis", "infection"]),
    ("What is anaphylaxis?", ["anaphylaxis", "allergic"]),
    ("What is meningitis?", ["meningitis", "meninges"]),
]


def main():
    load_dotenv()
    missing = [k for k in ("PINECONE_API_KEY", "GROQ_API_KEY") if not os.getenv(k)]
    if missing:
        raise SystemExit("Missing configuration: " + ", ".join(missing) + ". Set these in .env, then rerun.")

    embeddings = download_hugging_face_embeddings()
    store = PineconeVectorStore.from_existing_index("medical-chatbot", embeddings)
    retriever = store.as_retriever(search_type="similarity", search_kwargs={"k": 3})
    model = ChatGroq(model="openai/gpt-oss-120b")
    records = []
    hits = 0
    for number, (question, expected_phrases) in enumerate(QUESTIONS, 1):
        docs = retriever.invoke(question)
        contexts = [d.page_content for d in docs]
        found = [any(term.casefold() in chunk.casefold() for chunk in contexts) for term in expected_phrases]
        hit = any(found)
        hits += hit
        for variant, template in PROMPT_VARIANTS.items():
            prompt = ChatPromptTemplate.from_messages([("system", template), ("human", "Question: {input}")])
            answer = (prompt | model).invoke({"input": question, "context": "\n\n".join(contexts)}).content
            # A narrow, reproducible grounding proxy: answer must use a cited
            # term present in retrieved context and avoid unsupported claims.
            answer_l = answer.casefold()
            grounding_terms = [term for term in expected_phrases if term.casefold() in answer_l]
            grounded = bool(grounding_terms) and any(term.casefold() in " ".join(contexts).casefold() for term in grounding_terms)
            records.append({"id": number, "question": question, "variant": variant,
                            "answer": answer, "retrieved": contexts,
                            "expected_phrases": expected_phrases, "retrieval_hit_at_3": hit,
                            "grounding_proxy": grounded})

    Path("evaluation_results.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    grouped = defaultdict(list)
    for row in records:
        grouped[row["variant"]].append(row["grounding_proxy"])
    lines = ["# Local RAG evaluation", "", f"Questions: {len(QUESTIONS)}",
             f"Retrieval hit@3: {hits}/{len(QUESTIONS)} ({hits / len(QUESTIONS):.1%})",
             "", "Grounding proxy: answer contains one expected phrase that also occurs in retrieved context.",
             "This is an automatic screening measure, not a clinical correctness judgment.", "", "| Prompt | Grounding proxy |", "|---|---:|"]
    lines += [f"| {name} | {sum(scores)}/{len(scores)} ({sum(scores)/len(scores):.1%}) |" for name, scores in grouped.items()]
    Path("evaluation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
