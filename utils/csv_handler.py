"""
CSV file handling utilities
"""

import pandas as pd
import os
from datetime import datetime
from typing import Optional, Dict, List, Any
from config.database import DatabaseConfig


class CSVHandler:
    """Handle CSV file operations for query results"""
    
    def __init__(self, export_dir: Optional[str] = None):
        self.export_dir = export_dir or DatabaseConfig.EXPORT_DIR
        self._ensure_export_directory()
    
    def _ensure_export_directory(self):
        """Create export directory if it doesn't exist"""
        os.makedirs(self.export_dir, exist_ok=True)
    
    def save_dataframe(self, 
                      df: pd.DataFrame, 
                      filename: Optional[str] = None,
                      add_timestamp: bool = True) -> str:
        """
        Save DataFrame to CSV file
        
        Args:
            df: DataFrame to save
            filename: Custom filename (optional)
            add_timestamp: Whether to add timestamp to filename
            
        Returns:
            Full path to saved file
        """
        if filename is None:
            filename = "query_result.csv"
        
        # Add timestamp if requested
        if add_timestamp:
            base_name = os.path.splitext(filename)[0]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{base_name}_{timestamp}.csv"
        
        filepath = os.path.join(self.export_dir, filename)
        
        # Save with UTF-8 BOM for Excel compatibility
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        return filepath
    
    def load_csv(self, filename: str) -> pd.DataFrame:
        """
        Load CSV file into DataFrame
        
        Args:
            filename: Name of file to load
            
        Returns:
            DataFrame
        """
        filepath = os.path.join(self.export_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"CSV file not found: {filepath}")
        
        return pd.read_csv(filepath, encoding='utf-8-sig')
    
    def get_file_info(self, filename: str) -> Dict[str, Any]:
        """
        Get information about a CSV file
        
        Args:
            filename: Name of file
            
        Returns:
            Dictionary with file information
        """
        filepath = os.path.join(self.export_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"CSV file not found: {filepath}")
        
        stats = os.stat(filepath)
        df = pd.read_csv(filepath, nrows=0)  # Just read headers
        
        return {
            'filename': filename,
            'filepath': filepath,
            'size_bytes': stats.st_size,
            'size_mb': round(stats.st_size / (1024 * 1024), 2),
            'created': datetime.fromtimestamp(stats.st_ctime),
            'modified': datetime.fromtimestamp(stats.st_mtime),
            'columns': list(df.columns),
            'column_count': len(df.columns)
        }
    
    def list_csv_files(self) -> List[Dict[str, Any]]:
        """
        List all CSV files in export directory
        
        Returns:
            List of file information dictionaries
        """
        files = []
        
        for filename in os.listdir(self.export_dir):
            if filename.endswith('.csv'):
                try:
                    info = self.get_file_info(filename)
                    files.append(info)
                except Exception as e:
                    print(f"Error reading {filename}: {str(e)}")
        
        # Sort by modified time (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return files
    
    def delete_file(self, filename: str) -> bool:
        """
        Delete a CSV file
        
        Args:
            filename: Name of file to delete
            
        Returns:
            True if deleted, False otherwise
        """
        filepath = os.path.join(self.export_dir, filename)
        
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
            return False
        except Exception as e:
            print(f"Error deleting {filename}: {str(e)}")
            return False
    
    def clean_old_files(self, days_old: int = 30) -> int:
        """
        Delete CSV files older than specified days
        
        Args:
            days_old: Delete files older than this many days
            
        Returns:
            Number of files deleted
        """
        deleted_count = 0
        current_time = datetime.now().timestamp()
        max_age = days_old * 24 * 60 * 60  # Convert to seconds
        
        for filename in os.listdir(self.export_dir):
            if filename.endswith('.csv'):
                filepath = os.path.join(self.export_dir, filename)
                file_time = os.path.getmtime(filepath)
                
                if (current_time - file_time) > max_age:
                    if self.delete_file(filename):
                        deleted_count += 1
        
        return deleted_count
    
    def get_directory_size(self) -> Dict[str, Any]:
        """
        Get total size of export directory
        
        Returns:
            Dictionary with size information
        """
        total_size = 0
        file_count = 0
        
        for filename in os.listdir(self.export_dir):
            if filename.endswith('.csv'):
                filepath = os.path.join(self.export_dir, filename)
                total_size += os.path.getsize(filepath)
                file_count += 1
        
        return {
            'total_files': file_count,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'total_size_gb': round(total_size / (1024 * 1024 * 1024), 3)
        }
    
    def format_dataframe_for_display(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Format DataFrame for better display in UI
        
        Args:
            df: DataFrame to format
            
        Returns:
            Formatted DataFrame
        """
        df_copy = df.copy()
        
        # Format datetime columns
        for col in df_copy.columns:
            if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
                df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Format float columns to 2 decimal places
        for col in df_copy.select_dtypes(include=['float64']).columns:
            df_copy[col] = df_copy[col].round(2)
        
        return df_copy
    
    def export_with_metadata(self, 
                            df: pd.DataFrame, 
                            query_info: Dict[str, Any],
                            filename: Optional[str] = None) -> str:
        """
        Export DataFrame with metadata in separate file
        
        Args:
            df: DataFrame to save
            query_info: Dictionary with query metadata
            filename: Custom filename (optional)
            
        Returns:
            Path to data file
        """
        # Save data file
        data_path = self.save_dataframe(df, filename)
        
        # Create metadata file
        base_name = os.path.splitext(os.path.basename(data_path))[0]
        metadata_path = os.path.join(self.export_dir, f"{base_name}_metadata.txt")
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write("="*50 + "\n")
            f.write("Query Metadata\n")
            f.write("="*50 + "\n\n")
            
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Natural Query: {query_info.get('natural_query', 'N/A')}\n\n")
            
            f.write("Generated SQL:\n")
            f.write("-"*50 + "\n")
            f.write(f"{query_info.get('sql', 'N/A')}\n")
            f.write("-"*50 + "\n\n")
            
            f.write(f"Explanation: {query_info.get('explanation', 'N/A')}\n")
            f.write(f"Confidence: {query_info.get('confidence', 0):.2%}\n")
            f.write(f"Row Count: {query_info.get('row_count', 0)}\n")
            f.write(f"Tables Used: {', '.join(query_info.get('tables_used', []))}\n")
        
        return data_path