import { NextResponse } from 'next/server';

export const maxDuration = 120; // Allow up to 2 minutes

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const response = await fetch(`http://localhost:8000/api/v1/rules/${id}/apply`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Apply rule error:', error);
    return NextResponse.json(
      { error: 'Failed to apply rule' },
      { status: 500 }
    );
  }
}
