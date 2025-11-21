"""
Schema Vector Store Module
Stores database table schemas in a vector database (FAISS) for semantic search
"""
import os
import json
import pickle
from typing import List, Dict, Any, Optional
import numpy as np
from pathlib import Path

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: FAISS not available. Install with: pip install faiss-cpu")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available. Install with: pip install sentence-transformers")


class SchemaVectorStore:
    """Vector store for database table schemas"""
    
    def __init__(self, store_path: str = "./data/schema_vector_store", 
                 embedding_model: str = "all-MiniLM-L6-v2"):
        """
        Initialize schema vector store
        
        Args:
            store_path: Path to store vector index and metadata
            embedding_model: Name of the sentence transformer model to use
        """
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        self.index_path = self.store_path / "schema_index.faiss"
        self.metadata_path = self.store_path / "schema_metadata.pkl"
        
        # Initialize embedding model
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            self.embedding_model = SentenceTransformer(embedding_model)
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        else:
            self.embedding_model = None
            self.embedding_dim = 384  # Default dimension
        
        # Initialize FAISS index
        if FAISS_AVAILABLE:
            if self.index_path.exists():
                self.index = faiss.read_index(str(self.index_path))
                with open(self.metadata_path, 'rb') as f:
                    self.metadata = pickle.load(f)
            else:
                self.index = faiss.IndexFlatL2(self.embedding_dim)
                self.metadata = []
        else:
            self.index = None
            self.metadata = []
    
    def _format_schema_text(self, schema: Dict[str, Any]) -> str:
        """Format schema information as text for embedding"""
        table_name = schema.get('table_name', '')
        columns = schema.get('columns', [])
        primary_key = schema.get('primary_key', [])
        
        # Build descriptive text
        text_parts = [f"Table: {table_name}"]
        text_parts.append("Columns:")
        
        for col in columns:
            col_name = col.get('name', '')
            col_type = str(col.get('type', ''))
            nullable = "nullable" if col.get('nullable', True) else "not null"
            text_parts.append(f"  {col_name} ({col_type}, {nullable})")
        
        if primary_key:
            text_parts.append(f"Primary Key: {', '.join(primary_key)}")
        
        return "\n".join(text_parts)
    
    def add_schemas(self, schemas: Dict[str, Dict[str, Any]]):
        """
        Add multiple table schemas to the vector store
        
        Args:
            schemas: Dictionary mapping table names to schema dictionaries
        """
        if not FAISS_AVAILABLE or not SENTENCE_TRANSFORMERS_AVAILABLE:
            print("Warning: FAISS or sentence-transformers not available. Schemas will be stored in memory only.")
            for table_name, schema in schemas.items():
                self.metadata.append({
                    'table_name': table_name,
                    'schema': schema,
                    'schema_text': self._format_schema_text(schema)
                })
            return
        
        new_embeddings = []
        new_metadata = []
        
        for table_name, schema in schemas.items():
            schema_text = self._format_schema_text(schema)
            
            # Generate embedding
            embedding = self.embedding_model.encode(schema_text, convert_to_numpy=True)
            embedding = embedding.reshape(1, -1).astype('float32')
            
            new_embeddings.append(embedding)
            new_metadata.append({
                'table_name': table_name,
                'schema': schema,
                'schema_text': schema_text
            })
        
        # Add to FAISS index
        if new_embeddings:
            embeddings_array = np.vstack(new_embeddings)
            self.index.add(embeddings_array)
            self.metadata.extend(new_metadata)
        
        # Save to disk
        self.save()
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for relevant schemas based on natural language query
        
        Args:
            query: Natural language query
            top_k: Number of top results to return
            
        Returns:
            List of relevant schema dictionaries with similarity scores
        """
        if not FAISS_AVAILABLE or not SENTENCE_TRANSFORMERS_AVAILABLE:
            # Fallback: simple text matching
            query_lower = query.lower()
            results = []
            for meta in self.metadata:
                schema_text = meta.get('schema_text', '').lower()
                if query_lower in schema_text:
                    results.append({
                        'table_name': meta['table_name'],
                        'schema': meta['schema'],
                        'schema_text': meta['schema_text'],
                        'score': 1.0  # Dummy score
                    })
            return results[:top_k]
        
        if self.index.ntotal == 0:
            return []
        
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query, convert_to_numpy=True)
        query_embedding = query_embedding.reshape(1, -1).astype('float32')
        
        # Search in FAISS index
        distances, indices = self.index.search(query_embedding, min(top_k, self.index.ntotal))
        
        # Retrieve results
        results = []
        for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.metadata):
                meta = self.metadata[idx]
                results.append({
                    'table_name': meta['table_name'],
                    'schema': meta['schema'],
                    'schema_text': meta['schema_text'],
                    'score': float(1.0 / (1.0 + distance))  # Convert distance to similarity score
                })
        
        return results
    
    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Get all stored schemas"""
        schemas = {}
        for meta in self.metadata:
            schemas[meta['table_name']] = meta['schema']
        return schemas
    
    def clear(self):
        """Clear all stored schemas"""
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatL2(self.embedding_dim)
        self.metadata = []
        self.save()
    
    def save(self):
        """Save index and metadata to disk"""
        if FAISS_AVAILABLE and self.index is not None:
            faiss.write_index(self.index, str(self.index_path))
        with open(self.metadata_path, 'wb') as f:
            pickle.dump(self.metadata, f)
    
    def load(self):
        """Load index and metadata from disk"""
        if FAISS_AVAILABLE and self.index_path.exists():
            self.index = faiss.read_index(str(self.index_path))
        if self.metadata_path.exists():
            with open(self.metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)

