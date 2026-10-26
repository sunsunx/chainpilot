from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


DOCUMENTS_DIR = (
    Path(__file__).resolve().parent.parent / "documents"
)


def load_documents():
    documents = []

    for file_path in sorted(DOCUMENTS_DIR.glob("*.txt")):
        text = file_path.read_text(encoding="utf-8")

        documents.append(
            Document(
                page_content=text,
                metadata={"source": file_path.name},
            )
        )

    if not documents:
        raise ValueError(
            f"No documents found in {DOCUMENTS_DIR}"
        )

    return documents


def build_vector_store():
    documents = load_documents()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )

    chunks = splitter.split_documents(documents)

    embeddings = OllamaEmbeddings(
        model="nomic-embed-text"
    )

    vector_store = InMemoryVectorStore(embeddings)
    vector_store.add_documents(chunks)

    return vector_store


def answer_question(question, data_context=None):
    vector_store = build_vector_store()

    results = vector_store.similarity_search(
        question,
        k=2,
    )

    context = "\n\n".join(
        result.page_content
        for result in results
    )

    sources = [
        result.metadata["source"]
        for result in results
    ]

    llm = ChatOllama(
        model="llama3.2:3b",
        temperature=0,
    )

    if data_context is None:
        data_context = "No simulation data was provided."

    prompt = f"""
You are a supply chain planning assistant.

Answer the question using the policy documents and simulation data below.
Do not invent information.

Use policy documents for rules and recommended actions.
Use simulation data for current values, counts, averages, costs, and trends.
If the data does not contain the requested value, say that the value is not available.
If the question asks for supplier purchase price but the data only has transport cost,
say that supplier purchase price is not available.

Use clear, simple technical English.
Use short sentences.
Use active voice.
Use one idea in each sentence.
Use common words.
Avoid idioms and vague words.
Use bullet points for actions.
Put each action on its own line.
Use a numbered list with one action per line.
Answer in the same language as the question.
If the question contains Chinese characters, answer only in Traditional Chinese.
Do not use Thai, Japanese, or Simplified Chinese.
Use Chinese for every sentence and every action item.
If the question is in English, answer only in simple English.
Do not show internal field names such as hub_to_dc_sea, dc_to_cu, or supplier_to_hub.
Use the clear route names from the simulation data.
For a data question, give the value first. Do not add actions unless the question asks for actions.

Question:
{question}

Policy documents:
{context}

Simulation data:
{data_context}

Answer in simple English using short and clear sentences.

Provide:
1. A short answer
2. Recommended actions
"""

    answer = llm.invoke(prompt)

    answer_text = answer.content

    # Small local models can sometimes mix Thai characters into a Chinese answer.
    # Ask the same model to correct the answer once before showing it to the user.
    has_thai = any("\u0e00" <= character <= "\u0e7f" for character in answer_text)

    if has_thai and any("\u4e00" <= character <= "\u9fff" for character in question):
        repair_prompt = f"""
Rewrite the answer below.

Rules:
- Use Traditional Chinese only.
- Do not use Thai, Japanese, Simplified Chinese, or English sentences.
- Keep the numbers and facts unchanged.
- Use short sentences.
- Use one numbered action per line only if the original answer contains actions.
- Replace internal route names with clear names.

Original answer:
{answer_text}
"""
        answer = llm.invoke(repair_prompt)
        answer_text = answer.content

    if "simulation data" in data_context.lower():
        sources.append("simulation_data.csv")

    return answer_text, list(dict.fromkeys(sources))


if __name__ == "__main__":
    question = (
        "What should the planner do when "
        "supplier lead time increases?"
    )

    answer, sources = answer_question(question)

    print("=== AI Answer ===")
    print(answer)

    print("\n=== Sources ===")

    for source in sources:
        print(f"- {source}")
