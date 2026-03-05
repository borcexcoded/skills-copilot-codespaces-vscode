const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export interface Member {
  id: number;
  name: string;
}

export type MembersResponse = { total: number; members: Member[] };

export interface AttendanceRecord {
  id: number;
  name: string;
  time: string | null;
}

export interface AttendanceStats {
  period_days: number;
  total_records: number;
  unique_members: number;
  today_count: number;
  daily_breakdown: { date: string; count: number }[];
  top_attendees: { name: string; count: number }[];
}

export interface RecognitionResult {
  recognized: string[];
  attendance_marked: string[];
  total_faces: number;
}

// --- Members ---
export async function getMembers(): Promise<{ total: number; members: Member[] }> {
  const res = await fetch(`${API_BASE}/members`);
  if (!res.ok) throw new Error("Failed to fetch members");
  return res.json();
}

export async function registerMember(name: string, photo: File): Promise<{ message: string; id: number }> {
  const formData = new FormData();
  formData.append("name", name);
  formData.append("file", photo);

  const res = await fetch(`${API_BASE}/register`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || "Registration failed");
  }
  return res.json();
}

export async function deleteMember(id: number): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/members/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete member");
  return res.json();
}

// --- Attendance ---
export async function getAttendance(params?: {
  date?: string;
  name?: string;
  limit?: number;
  offset?: number;
}): Promise<{ total: number; records: AttendanceRecord[] }> {
  const searchParams = new URLSearchParams();
  if (params?.date) searchParams.set("date", params.date);
  if (params?.name) searchParams.set("name", params.name);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));

  const res = await fetch(`${API_BASE}/attendance?${searchParams.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch attendance");
  return res.json();
}

export async function getTodayAttendance(): Promise<{
  date: string;
  total_records: number;
  unique_members: number;
  members: string[];
  records: AttendanceRecord[];
}> {
  const res = await fetch(`${API_BASE}/attendance/today`);
  if (!res.ok) throw new Error("Failed to fetch today's attendance");
  return res.json();
}

export async function getAttendanceStats(days?: number): Promise<AttendanceStats> {
  const params = days ? `?days=${days}` : "";
  const res = await fetch(`${API_BASE}/attendance/stats${params}`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function deleteAttendanceRecord(id: number): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/attendance/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete record");
  return res.json();
}

// --- Recognition ---
export async function recognizeFaces(photo: File): Promise<RecognitionResult> {
  const formData = new FormData();
  formData.append("file", photo);

  const res = await fetch(`${API_BASE}/recognize`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || "Recognition failed");
  }
  return res.json();
}

// --- Health ---
export async function healthCheck(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("API not available");
  return res.json();
}
