
candidate_schema = {
  "type": "object",
  "properties": {
    "company": {
      "type": "string",
      "description": "The company that the job description belongs to"
    },
    "role": {
      "type": "string",
      "description": "The role that the job description belongs to"
    },
    "swot_analysis": {
      "type": "object",
      "description": "SWOT analysis with structured entries",
      "properties": {
        "strengths": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "description": {"type": "string"}
            },
            "required": ["title", "description"]
          }
        },
        "weaknesses": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "description": {"type": "string"}
            },
            "required": ["title", "description"]
          }
        },
        "opportunities": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "description": {"type": "string"}
            },
            "required": ["title", "description"]
          }
        },
        "threats": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "description": {"type": "string"}
            },
            "required": ["title", "description"]
          }
        }
      },
      "required": ["strengths", "weaknesses", "opportunities", "threats"]
    },
    "skill_assessment": {
      "type": "object",
      "properties": {
        "match_percentage": {
          "type": "number",
          "minimum": 0,
          "maximum": 100,
          "description": "Overall skill match percentage from 0 to 100"
        },
        "matched_skills": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "description": {"type": "string"},
              "rating": {"type": "string"}
            },
            "required": ["title", "description", "rating"]
          }
        },
        "partial_matches": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "description": {"type": "string"},
              "rating": {"type": "string"}
            },
            "required": ["title", "description", "rating"]
          }
        },
        "missing_skills": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "description": {"type": "string"}
            },
            "required": ["title", "description"]
          }
        }
      },
      "required": ["match_percentage", "matched_skills", "partial_matches", "missing_skills"]
    },
    "concept_refresh": {
      "type": "array",
      "description": "Concepts to revise before the interview",
      "items": {
        "type": "object",
        "properties": {
          "topic": {"type": "string"},
          "context": {
            "type": "string",
            "description": "Where it is mentioned (JD/resume)"
          },
          "review_notes": {
            "type": "string",
            "description": "Short description of what to revise"
          },
          "article_resource": {"type": "string"}
        },
        "required": ["topic", "context", "review_notes", "article_resource"]
      },
      "items": {
        "type": "object",
        "properties": {
          "topic": {"type": "string"},
          "context": {
            "type": "string",
            "description": "Where it is mentioned (JD/resume)"
          },
          "review_notes": {
            "type": "string",
            "description": "Short description of what to revise"
          },
          "video_resource": {"type": "string"},
        },
        "required": ["topic", "context", "review_notes", "video_resource"]
      }
    },
    "interview_questions": {
      "type": "array",
      "description": "Key interview questions and answers",
      "items": {
        "type": "object",
        "properties": {
          "category": {
            "type": "string",
            "enum": ["Technical", "Behavioral", "Experience", "Project"]
          },
          "difficulty": {
            "type": "string",
            "enum": ["Easy", "Medium", "Hard"]
          },
          "question": {"type": "string"},
          "answer": {"type": "string"}
        },
        "required": ["category", "difficulty", "question", "answer"]
      }
    },
    "company_insights": {
      "type": "object",
      "properties": {
        "company_overview": {"type": "string"},
        "culture_points": {
          "type": "array",
          "items": {"type": "string"}
        },
        "company_values": {
          "type": "array",
          "items": {"type": "string"}
        },
        "interview_style": {"type": "string"},
        "expectations": {"type": "string"},
        "additional_info": {"type": "string"},
        "fallback": {
          "type": "string",
          "description": "Fallback text if company insights are not available"
        }
      },
      "required": ["company_overview", "culture_points", "company_values", "interview_style", "expectations", "additional_info"]
    }
  },
  "required": [
    "company",
    "role",
    "swot_analysis",
    "skill_assessment",
    "concept_refresh",
    "interview_questions",
    "company_insights"
  ]
}

interviewer_schema = {
  "type": "object",
  "properties": {
    "candidate_overview": {
      "type": "object",
      "properties": {
        "full_name": {"type": "string"},
        "current_job_title": {"type": "string"},
        "email": {"type": "string"},
        "phone_number": {"type": "string"},
        "location": {"type": "string"},
        "top_skills": {
          "type": "array",
          "items": {"type": "string"}
        },
        "candidate_summary": {"type": "string"}
      },
      "required": ["full_name", "current_job_title", "email", "location", "candidate_summary", "top_skills"]
    },
    "compatibility_score": {
      "type": "object",
      "properties": {
        "overall_score": {"type": "number", "minimum": 0, "maximum": 100, "description": "Score from 0 to 100"},
        "match": {"type": "string", "enum": ["excellent", "good", "poor"]},
        "technical_skills_score": {"type": "number", "minimum": 0, "maximum": 100, "description": "Score from 0 to 100"},
        "education_score": {"type": "number", "minimum": 0, "maximum": 100, "description": "Score from 0 to 100"},
        "experience_score": {"type": "number", "minimum": 0, "maximum": 100, "description": "Score from 0 to 100"},
        "cultural_fit_score": {"type": "number", "minimum": 0, "maximum": 100, "description": "Score from 0 to 100"}
      },
      "required": ["overall_score", "match", "technical_skills_score", "education_score", "experience_score"]

    },
    "skills_assessment": {
      "type": "object",
      "properties": {
        "data": {
          "type": "object",
          "properties": {
            "skillsByCategory": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "category": { "type": "string" },
                  "skills": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "name": { "type": "string" },
                        "level": { "type": "number", "minimum": 0, "maximum": 5, "description": "Candidate proficiency from 0 to 5" },
                        "required": { "type": "number", "minimum": 0, "maximum": 5, "description": "Proficiency the role requires, from 0 to 5" },
                        "status": {
                          "type": "string",
                          "enum": ["exceeds", "meets", "below", "missing"]
                        }
                      },
                      "required": ["name", "level", "required", "status"]
                    }
                  }
                },
                "required": ["category", "skills"]
              }
            },
            "skillsDistribution": {
              "type": "object",
              "properties": {
                "exceeds": { "type": "number" },
                "meets": { "type": "number" },
                "below": { "type": "number" },
                "missing": { "type": "number" }
              },
              "required": ["exceeds", "meets", "below", "missing"]
            }
          },
          "required": ["skillsByCategory", "skillsDistribution"]
        }
      },
      "required": ["data"]
    },
    "education": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "degree_name": {"type": "string"},
          "institution": {"type": "string"},
          "location": {"type": "string"},
          "major": {"type": "string"},
          "notable_points": {
            "type": "array",
            "items": {"type": "string"}
          }
        },
        "required": ["degree_name", "institution", "notable_points"]
      }
    },
    "experience": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "company": {"type": "string"},
          "location": {"type": "string"},
          "start_date": {"type": "string"},
          "end_date": {"type": "string"},
          "responsibilities": {
            "type": "array",
            "items": {"type": "string"}
          },
          "relevance_to_job": {"type": "string", "enum": ["High", "Medium", "Low"]}
        },
        "required": ["title", "company", "responsibilities", "relevance_to_job"]
      }
    },
    "skill_gaps_and_concerns": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "skill_name": {"type": "string"},
          "recommendation": {"type": "string"},
          "gap_level": {"type": "string", "enum": ["Critical Gap", "Minor Gap"]},
          "gap_severity": {"type": "string", "enum": ["High", "Medium", "Low"]}
        },
        "required": ["skill_name", "recommendation", "gap_level", "gap_severity"]
      }
    },
    "recommended_screening_questions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
          "category": {"type": "string", "enum": ["technical", "behavioral", "experience", "project"]},
          "question": {"type": "string"},
          "purpose": {"type": "string"}
        },
        "required": ["priority", "category", "question", "purpose"]
      }
    },
    "interview_recommendation": {
      "type": "object",
      "properties": {
        "proceed": {"type": "string", "enum": ["Strong Yes", "Yes", "Consider", "No"]},
        "summary": {"type": "string"},
        "key_strengths": {
          "type": "array",
          "items": {"type": "string"}
        },
        "concerns": {
          "type": "array",
          "items": {"type": "string"}
        },
        "recommended_next_steps": {
          "type": "array",
          "items": {"type": "string"}
        }
      },
      "required": ["proceed", "summary", "key_strengths", "concerns"]
    }
  }
}
