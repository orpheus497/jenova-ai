import os
import json
import chromadb
from chromadb.utils import embedding_functions

import uuid

from jenova.utils.json_parser import extract_json

class ProceduralMemory:
    def __init__(self, config, ui_logger, file_logger, db_path, llm):
        self.config = config
        self.ui_logger = ui_logger
        self.file_logger = file_logger
        self.db_path = db_path
        self.llm = llm
        os.makedirs(self.db_path, exist_ok=True)
        
        client = chromadb.PersistentClient(path=self.db_path)
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=config['model']['embedding_model'])
        self.collection = client.get_or_create_collection(name="procedural_steps", embedding_function=self.embedding_function)

    def add_procedure(self, procedure: str, username: str, goal: str = None, steps: list = None, context: str = None):
        if not goal or not steps or not context:
            prompt = f'''Analyze the following procedure and extract the goal, the steps, and the context. Respond with a JSON object containing "goal" (a string), "steps" (a list of strings), and "context" (a string).

Ensure your response is a single, valid JSON object and nothing else.

Procedure: "{procedure}"

JSON Response:'''
            try:
                response_str = self.llm.generate(prompt, temperature=0.2)
                response_data = extract_json(response_str)
                goal = response_data.get('goal')
                steps = response_data.get('steps', [])
                context = response_data.get('context')
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                goal = None
                steps = None
                context = None
            except Exception as e:
                self.file_logger.log_error(f"Error during procedure metadata extraction: {e}")
                goal = None
                steps = None
                context = None

        metadata = {
            "username": username,
            "goal": goal,
            "steps": json.dumps(steps),
            "context": context
        }
        
        doc_id = f"proc_{uuid.uuid4()}"
        self.collection.add(ids=[doc_id], documents=[procedure], metadatas=[metadata])
        self.file_logger.log_info(f"Added procedure {doc_id} to procedural memory.")

    def search(self, query: str, username: str, n_results: int = 2) -> list[tuple[str, float]]:
        if self.collection.count() == 0: return []
        n_results = min(n_results, self.collection.count())
        try:
            results = self.collection.query(query_texts=[query], n_results=n_results, where={"username": username})
            if not results['documents']: return []
            return list(zip(results['documents'][0], results['distances'][0]))
        except Exception as e:
            self.file_logger.log_error(f"Error during procedural memory search: {e}")
            return []