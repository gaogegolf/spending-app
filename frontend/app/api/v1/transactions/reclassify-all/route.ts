import { NextResponse } from 'next/server';

export const maxDuration = 120; // Allow up to 2 minutes for this endpoint

export async function POST() {
  try {
    const response = await fetch('http://localhost:8000/api/v1/transactions/reclassify-all', {
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
    console.error('Reclassify error:', error);
    return NextResponse.json(
      { error: 'Failed to reclassify transactions' },
      { status: 500 }
    );
  }
}
