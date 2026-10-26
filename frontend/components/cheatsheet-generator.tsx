"use client";

import type React from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { FileUploader } from "@/components/file-uploader";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useToast } from "./ui/use-toast";
import { useDispatch, useSelector } from "react-redux";
import { RootState } from "../redux/store";
import { User, Users } from "lucide-react";
import {
  setCurrentCheatsheet,
  addCheatsheet,
} from "@/redux/slices/cheatsheetSlice";
import { apiBaseURL } from "../utils";
import Loading from "@/components/loading";

export function CheatsheetGenerator() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [jobDescription, setJobDescription] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isInterviewer, setIsInterviewer] = useState(false);
  const [cheatsheetType, setCheatsheetType] = useState("candidate");
  const router = useRouter();
  const { toast } = useToast();
  const dispatch = useDispatch();
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);

  const wordCount =
    jobDescription.trim() === ""
      ? 0
      : jobDescription.trim().split(/\s+/).length;

  const pollTask = async (taskId: string) => {
    const deadline = Date.now() + 5 * 60 * 1000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      const res = await fetch(`${apiBaseURL}/cheatsheet/task-status/${taskId}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error("Failed to check cheatsheet status");
      const status = await res.json();
      if (status.status === "SUCCESS") return status.data;
      if (status.status === "FAILURE") throw new Error(status.error);
    }
    throw new Error("Cheatsheet generation timed out. Please try again.");
  };

  const handleRoleToggle = (role: "candidate" | "interviewer") => {
    setIsInterviewer(role === "interviewer");
    setCheatsheetType(role);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!uploadedFile) {
      toast({
        title: "Resume required",
        description: "Please upload your resume to continue",
        variant: "destructive",
      });
      return;
    }

    if (!jobDescription.trim()) {
      toast({
        title: "Job description required",
        description: "Please enter the job description to continue",
        variant: "destructive",
      });
      return;
    }

    if (wordCount < 120) {
      toast({
        title: "Job description too short",
        description: "Please provide at least 120 words for better results.",
        variant: "destructive",
      });
      return;
    }

    setIsSubmitting(true);

    const formData = new FormData();
    formData.append("resume_pdf", uploadedFile);
    formData.append("job_description", jobDescription);
    formData.append("cheatsheet_type", cheatsheetType);
    try {
      const response = await fetch(`${apiBaseURL}/cheatsheet/generate`, {
        method: "POST",
        body: formData,
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "Failed to generate cheatsheet");
      }

      const { task_id } = await response.json();
      const cheatsheet = await pollTask(task_id);

      dispatch(addCheatsheet(cheatsheet));
      dispatch(setCurrentCheatsheet(cheatsheet));

      await new Promise((resolve) => setTimeout(resolve, 100));
      router.push(`/results/${cheatsheet.id}`);
    } catch (err) {
      console.error(err);
      toast({
        title: "Error",
        description:
          err instanceof Error
            ? err.message
            : "Something went wrong while generating the cheatsheet.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFileUploaded = (file: File) => {
    setResumeFile(file);
  };

  return (
    <>
      {isSubmitting ? (
        <Loading />
      ) : (
        <section className="py-16 px-4 md:px-6">
          <div className="container mx-auto max-w-4xl">
            <div className="text-center mb-10">
              <h1 className="text-4xl font-bold mb-3 bg-gradient-to-r from-teal-600 to-teal-400 bg-clip-text text-transparent">
                Generate Your Interview Cheatsheet
              </h1>
              <p className="text-gray-600 text-lg max-w-2xl mx-auto">
                Upload your resume and enter the job description to create your
                personalized interview guide
              </p>
            </div>
            <Card className="shadow-lg">
              <CardContent className="p-6">
                <form onSubmit={handleSubmit} className="space-y-6">
                  <div className="flex justify-center mb-2">
                    <div className="inline-flex items-center bg-gray-100 p-1 rounded-full">
                      <div
                        className={`flex items-center gap-2 px-4 py-2 rounded-full cursor-pointer transition-colors ${
                          cheatsheetType === "candidate"
                            ? "bg-white shadow-sm text-teal-700"
                            : "text-gray-600"
                        }`}
                        onClick={() => handleRoleToggle("candidate")}
                      >
                        <User className="h-4 w-4" />
                        <span className="font-medium">Candidate</span>
                      </div>

                      <div
                        className={`flex items-center gap-2 px-4 py-2 rounded-full cursor-pointer transition-colors ${
                          cheatsheetType === "interviewer"
                            ? "bg-white shadow-sm text-teal-700"
                            : "text-gray-600"
                        }`}
                        onClick={() => handleRoleToggle("interviewer")}
                      >
                        <Users className="h-4 w-4" />
                        <span className="font-medium">Interviewer</span>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-lg font-medium mb-2">
                      Upload Your Resume
                    </h3>
                    <FileUploader
                      onFileUploaded={() => console.log("File uploaded")}
                      onFileSelect={(file) => setUploadedFile(file)}
                    />
                  </div>

                  <div>
                    <h3 className="text-lg font-medium mb-2">
                      Enter Job Description
                    </h3>
                    <Textarea
                      placeholder="Tell us everything about the role — outline key responsibilities, required skills, qualifications, experience level, company culture, and any other relevant details. The more specific, the better!"
                      className="min-h-[150px]"
                      value={jobDescription}
                      onChange={(e) => setJobDescription(e.target.value)}
                      required
                    />
                    <p className="text-sm mt-1 text-gray-500">
                      {wordCount} words
                    </p>
                    {wordCount > 0 && wordCount < 120 && (
                      <p className="text-sm text-red-500">
                        Please write a more detailed job description (at least
                        120 words).
                      </p>
                    )}
                  </div>

                  <Button
                    className="w-full"
                    size="lg"
                    type="submit"
                    disabled={isSubmitting || wordCount < 120}
                  >
                    {isSubmitting
                      ? "Generating..."
                      : "Generate Interview Cheatsheet"}
                  </Button>

                  <p className="text-sm text-gray-400 text-center mt-2">
                    To get the best results, use a real and specific job
                    description and resume. Our AI needs detailed information to
                    generate accurate interview guides.
                  </p>
                </form>
              </CardContent>
            </Card>
          </div>
        </section>
      )}
    </>
  );
}
