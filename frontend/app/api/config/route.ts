import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
  return NextResponse.json({ backendUrl });
}
