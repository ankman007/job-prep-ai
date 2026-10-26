"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface SkillCategory {
  category: string;
  skills: {
    name: string;
    level: number;
    required: number;
    status: "exceeds" | "meets" | "below" | "missing";
  }[];
}

interface SkillsAssessmentProps {
  data: {
    skillsByCategory: SkillCategory[];
    skillsDistribution: {
      exceeds: number;
      meets: number;
      below: number;
      missing: number;
    };
  };
}

export function SkillsAssessment({ data }: SkillsAssessmentProps) {
  console.log("SkillsAssessment data", data);
  const [isExpanded, setIsExpanded] = useState(true);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "exceeds":
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case "meets":
        return <CheckCircle className="h-5 w-5 text-teal-500" />;
      case "below":
        return <AlertCircle className="h-5 w-5 text-amber-500" />;
      case "missing":
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return null;
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case "exceeds":
        return "Exceeds";
      case "meets":
        return "Meets";
      case "below":
        return "Below";
      case "missing":
        return "Missing";
      default:
        return "";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "exceeds":
        return "text-green-600 bg-green-50";
      case "meets":
        return "text-teal-600 bg-teal-50";
      case "below":
        return "text-amber-600 bg-amber-50";
      case "missing":
        return "text-red-600 bg-red-50";
      default:
        return "";
    }
  };

  const formatNumber = (data: any) => {
    const num = Number(data);
    return Number.isInteger(num) ? num : num.toFixed(1);
  };

  // Older cheatsheets store levels as 0-1, newer ones as 0-5
  const levelScale = data.skillsByCategory.every((category) =>
    category.skills.every((skill) => skill.level <= 1 && skill.required <= 1)
  )
    ? 5
    : 1;

  const getLevelBar = (level: number, required: number, status: string) => {
    const maxLevel = 5;
    const scaledLevel = Math.min(Math.round(level * levelScale), 5);
    const bars = [];

    for (let i = 1; i <= maxLevel; i++) {
      let barClass = "h-2 w-4 rounded-sm mx-0.5 ";

      if (i <= scaledLevel) {
        if (status === "exceeds") barClass += "bg-green-500";
        else if (status === "meets") barClass += "bg-teal-500";
        else if (status === "below") barClass += "bg-amber-500";
        else barClass += "bg-red-500";
      } else {
        barClass += "bg-gray-200";
      }

      bars.push(<div key={i} className={barClass}></div>);
    }

    return (
      <div className="flex items-center">
        <div className="flex">{bars}</div>
        <div className="ml-2 text-xs text-gray-500">
          {formatNumber((level * levelScale).toFixed(1))}/{formatNumber((required * levelScale).toFixed(1))} required
        </div>
      </div>
    );
  };

  const { exceeds, meets, below, missing } = data.skillsDistribution;
  const total = exceeds + meets + below + missing;

  return (
    <Card>
      <CardHeader
        className="pb-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center justify-between">
          <CardTitle>Skills Assessment</CardTitle>
          {isExpanded ? (
            <ChevronUp className="h-5 w-5 text-gray-500" />
          ) : (
            <ChevronDown className="h-5 w-5 text-gray-500" />
          )}
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent>
          <div className="mb-6">
            <h3 className="text-sm font-medium mb-3">Skills Distribution</h3>
            <div className="flex h-4 rounded-full overflow-hidden">
              <div
                className="bg-green-500"
                style={{ width: `${(exceeds / total) * 100}%` }}
                title={`Exceeds: ${exceeds} skills`}
              ></div>
              <div
                className="bg-teal-500"
                style={{ width: `${(meets / total) * 100}%` }}
                title={`Meets: ${meets} skills`}
              ></div>
              <div
                className="bg-amber-500"
                style={{ width: `${(below / total) * 100}%` }}
                title={`Below: ${below} skills`}
              ></div>
              <div
                className="bg-red-500"
                style={{ width: `${(missing / total) * 100}%` }}
                title={`Missing: ${missing} skills`}
              ></div>
            </div>
            <div className="flex justify-between mt-2 text-xs text-gray-500">
              <div className="flex items-center">
                <div className="w-3 h-3 bg-green-500 rounded-sm mr-1"></div>
                <span>Exceeds ({exceeds})</span>
              </div>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-teal-500 rounded-sm mr-1"></div>
                <span>Meets ({meets})</span>
              </div>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-amber-500 rounded-sm mr-1"></div>
                <span>Below ({below})</span>
              </div>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-red-500 rounded-sm mr-1"></div>
                <span>Missing ({missing})</span>
              </div>
            </div>
          </div>

          <Tabs defaultValue={data.skillsByCategory[0].category}>
            <TabsList className="w-full mb-4 overflow-x-auto flex-nowrap">
              {data.skillsByCategory.map((category, index) => (
                <TabsTrigger
                  key={index}
                  value={category.category}
                  className="flex-shrink-0"
                >
                  {category.category}
                </TabsTrigger>
              ))}
            </TabsList>

            {data.skillsByCategory.map((category, index) => (
              <TabsContent key={index} value={category.category}>
                <div className="space-y-3">
                  {category.skills.map((skill, skillIndex) => (
                    <div key={skillIndex} className="border rounded-md p-3">
                      <div className="flex justify-between items-start">
                        <div className="flex items-center">
                          {getStatusIcon(skill.status)}
                          <h4 className="font-medium ml-2">{skill.name}</h4>
                          <span
                            className={`ml-2 text-xs px-2 py-0.5 rounded-full ${getStatusColor(
                              skill.status
                            )}`}
                          >
                            {getStatusText(skill.status)}
                          </span>
                        </div>
                      </div>
                      <div className="mt-2">
                        {getLevelBar(skill.level, skill.required, skill.status)}
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      )}
    </Card>
  );
}
