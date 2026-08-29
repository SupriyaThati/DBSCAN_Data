# Merge — Smart Data Migration & Duplicate Detection

A Flask-based data migration tool that transfers customer records from a legacy database to a new database while automatically identifying potential duplicate customers using fuzzy matching and machine learning clustering.

Before migration, users can review suspected duplicate groups through a web dashboard and decide whether to merge records or keep them separate, helping maintain data quality in the target system.

---

## Features

* Migrate customer data between databases
* Detect potential duplicate customer records
* Fuzzy matching on names using RapidFuzz
* Email and phone-based similarity scoring
* DBSCAN clustering for grouping related duplicate records
* Interactive dashboard for duplicate review
* Manual merge or keep-separate decisions
* Demo mode with sample data for quick evaluation
* Supports MySQL databases via PyMySQL

---

## How It Works

### 1. Data Extraction

Customer records are loaded from the source database.

### 2. Data Normalization

The system standardizes:

* Names
* Phone numbers
* Email addresses

to improve matching accuracy.

### 3. Duplicate Detection

A weighted similarity score is calculated using:

| Field | Default Weight |
| ----- | -------------- |
| Name  | 35%            |
| Phone | 35%            |
| Email | 30%            |

The project uses:

* **RapidFuzz** for fuzzy string matching
* **DBSCAN (Scikit-Learn)** for clustering related records

This enables identification of both simple duplicate pairs and larger duplicate groups.

### 4. Human Review

Potential duplicate groups are displayed in the dashboard where users can:

* Merge into one record
* Keep records separate

### 5. Migration

Approved records are migrated to the target database.

---

## Project Structure

```text
migration_tool/
├── app.py                 # Flask backend and API routes
├── migration_engine.py    # Source/target database operations
├── duplicate_detector.py  # Duplicate detection logic
├── config.py             # Configuration settings
├── schema.sql            # Database schema
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   └── js/app.js
└── sample_data/
```

---

## Technology Stack

### Backend

* Python
* Flask

### Data Processing

* Pandas

### Machine Learning

* Scikit-Learn (DBSCAN)

### Similarity Matching

* RapidFuzz

### Database

* MySQL
* PyMySQL

### Frontend

* HTML
* CSS
* JavaScript

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/yourusername/merge-smart-data-migration.git
cd merge-smart-data-migration
```

### Create a Virtual Environment

```bash
python -m venv venv
```

Activate:

**Linux / macOS**

```bash
source venv/bin/activate
```

**Windows**

```bash
venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Application

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

---

## Configuration

Database connections and duplicate-detection settings can be configured through `config.py`.

Examples include:

* Source database credentials
* Target database credentials
* Matching weights
* Duplicate detection threshold
* Table and column mappings

---

## Sample Use Case

A company is migrating customer data from a legacy CRM system to a new platform.

Before migration, the tool identifies records such as:

```text
John Smith
John A. Smith
J. Smith
```

with matching phone numbers or emails and groups them as likely duplicates.

Users review these suggestions and decide whether to merge or retain the records before migration proceeds.

---

## Future Enhancements

* Automated field-level merge strategies
* Merge history and audit logs
* Authentication and role-based access
* Batch migration scheduling
* Advanced duplicate detection models
* Support for additional database systems

---

## Key Learning Outcomes

This project demonstrates:

* Data migration workflows
* Data cleansing and normalization
* Fuzzy matching techniques
* Machine learning clustering
* Backend API development with Flask
* Database integration using MySQL
* Interactive review workflows for data quality management

---

## License

This project is available for educational and portfolio purposes.
