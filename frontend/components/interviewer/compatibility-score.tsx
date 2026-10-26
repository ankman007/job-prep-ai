"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"

interface RawCompatibilityData {
  education_score: number
  experience_score: number
  technical_skills_score: number
  cultural_fit_score: number
  overall_score: number
  match: string
}

interface CompatibilityScoreProps {
  data: RawCompatibilityData
}

export function CompatibilityScore({ data }: CompatibilityScoreProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-green-600"
    if (score >= 60) return "text-teal-600"
    if (score >= 40) return "text-amber-600"
    return "text-red-600"
  }

  const getScoreText = (score: number) => {
    if (score >= 80) return "Excellent Match"
    if (score >= 60) return "Good Match"
    if (score >= 40) return "Moderate Match"
    return "Low Match"
  }

  // Older cheatsheets store scores as 0-1, newer ones as 0-100
  const formatScore = (score: number) => Math.round(score <= 1 ? score * 100 : score)

  const categories = [
    { name: "Education", score: formatScore(data.education_score) },
    { name: "Experience", score: formatScore(data.experience_score) },
    { name: "Technical Skills", score: formatScore(data.technical_skills_score) },
    { name: "Cultural Fit", score: formatScore(data.cultural_fit_score) },
  ]

  const overallScore = formatScore(data.overall_score)

  return (
    <Card>
      <CardHeader className="pb-3 cursor-pointer hover:bg-gray-50" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="flex items-center justify-between">
          <CardTitle>Compatibility Score</CardTitle>
          {isExpanded ? (
            <ChevronUp className="h-5 w-5 text-gray-500" />
          ) : (
            <ChevronDown className="h-5 w-5 text-gray-500" />
          )}
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent>
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center rounded-full bg-gray-100 p-6 mb-2">
              <div className="text-4xl font-bold text-teal-600">{overallScore}%</div>
            </div>
            <p className={`font-medium ${getScoreColor(overallScore)}`}>{getScoreText(overallScore)}</p>
          </div>

          <div className="space-y-4">
            {categories.map((category, index) => (
              <div key={index}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-medium">{category.name}</span>
                  <span className="text-sm font-medium">{category.score}%</span>
                </div>
                <Progress
                  value={category.score}
                  className="h-2 bg-teal-100"
                />
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  )
}
