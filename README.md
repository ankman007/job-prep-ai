RAG Architecture - Job Fit AI
Overview

Job Fit AI is a RAG-based interview preparation platform that generates personalized interview insights by analyzing resumes, job descriptions, interview knowledge bases, and company-related information.

The system follows three major phases:

Data Ingestion
Retrieval
Generation
Phase 1: Data Ingestion

The goal of this phase is to transform raw interview preparation content into a searchable knowledge base.

1. Data Collection

We collected and processed approximately 4.5GB of interview preparation data from various sources, including:

Technical interview questions
System design resources
Programming concepts
Behavioral interview materials
Company-specific interview experiences
Career preparation content

This dataset serves as the foundation of the platform's knowledge base.

2. Data Cleaning and Preprocessing

Before indexing the data, extensive preprocessing was performed to improve retrieval quality.

The cleaning pipeline included:

Removal of unnecessary formatting
Whitespace normalization
Duplicate content removal
Low-information content filtering
Noise reduction
Text standardization

This ensured that only high-quality and semantically meaningful content was stored.

3. Document Chunking

Large documents cannot be embedded effectively as a single unit.

Therefore, documents were split into smaller chunks using LangChain's Recursive Character Text Splitter.

Configuration
Chunk Size: 600 characters
Chunk Overlap: 100 characters

The recursive splitter attempts to preserve document structure by splitting at:

Paragraph boundaries
Sentence boundaries
Whitespace
Character level (if necessary)

Different chunking strategies were also applied depending on whether the content contained plain text or code snippets.

This improves retrieval accuracy while preserving context.

4. Embedding Generation

After chunking, each chunk is converted into a dense vector representation using a local embedding model.

An embedding transforms human-readable text into a numerical vector that captures semantic meaning.

As a result:

Similar concepts are placed close together in vector space.
Semantically related interview topics can be discovered even when exact keywords do not match.

To keep costs low and maintain full control over the pipeline, embeddings were generated locally on a machine with approximately 20GB RAM, eliminating dependency on external embedding APIs.

5. Vector Storage and Indexing

The generated embeddings are stored in ChromaDB.

Each vector is stored together with:

Original text chunk
Metadata
Source information

ChromaDB builds efficient vector indexes that enable fast semantic similarity searches across millions of text chunks.

Phase 2: Retrieval

The retrieval phase is responsible for finding the most relevant information needed to answer a specific user request.

Unlike a traditional chatbot, users do not engage in a back-and-forth conversation.

Instead, users upload:

Their Resume
Target Job Description

These become the primary inputs for the retrieval pipeline.

1. Query Processing

The uploaded resume and job description are analyzed and transformed into search queries.

Relevant concepts, skills, technologies, and job requirements are extracted and embedded using the same embedding model used during ingestion.

Using the same embedding model ensures that both stored documents and incoming queries exist in the same semantic vector space.

2. Hybrid Retrieval

To maximize relevance, the system uses Hybrid Search.

Dense Retrieval

Semantic vector search is performed in ChromaDB.

This helps retrieve conceptually related content even when wording differs.

Example:

"REST API authentication"
"JWT authorization"

can still be matched because they are semantically related.

Sparse Retrieval

Keyword-based retrieval is also performed to capture exact matches.

This is useful for:

Technology names
Frameworks
Company-specific terms
Programming languages
3. Result Fusion

Results from both retrieval methods are combined and ranked.

The hybrid approach provides:

Better relevance
Reduced vocabulary mismatch issues
Improved retrieval accuracy
Lower hallucination risk

The final output is a ranked list of highly relevant knowledge chunks that will be provided to the LLM.

Phase 3: Generation

Once relevant context has been retrieved, the generation pipeline creates personalized interview insights.

1. Prompt Augmentation

Retrieved knowledge is combined with:

Resume information
Job description
Candidate profile
Retrieved interview knowledge

This creates a rich context package for the LLM.

2. Context Injection

The retrieved context is injected directly into the prompt.

The LLM is explicitly instructed to generate responses only using the supplied information whenever possible.

This significantly reduces hallucinations and improves factual consistency.

3. Structured Output Enforcement

One of the key improvements in the system is the use of JSON Schema Enforcement.

Instead of generating free-form text, the model must produce a predefined structured response.

Benefits include:

Predictable outputs
Easier frontend integration
Reliable parsing
Consistent user experience

This was implemented using structured prompt engineering and schema validation techniques.

4. Response Generation

The system generates personalized outputs for two user groups.

For Job Seekers

The platform generates:

Resume SWOT Analysis
Skill Gap Analysis
Learning Recommendations
Concept Revision Areas
Predicted Interview Questions
Company Insights
For Interviewers

The platform generates:

Candidate Summary
Experience Analysis
Education Review
Job Compatibility Score
Skill Assessment
Skill Gap Detection
Potential Concerns
Recommended Screening Questions
Interview Strategy Suggestions
5. Response Delivery

The final structured response is returned to the Next.js frontend, where it is rendered into a user-friendly dashboard.

The complete architecture is deployed using:

FastAPI
LangChain
ChromaDB
PostgreSQL
Next.js
Redux
Docker
