const TIKTOK_VERIFICATION_FILE = /^tiktok([A-Za-z0-9]+)\.txt$/;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ verification: string }> },
) {
  const { verification } = await params;
  const match = TIKTOK_VERIFICATION_FILE.exec(verification);

  if (!match) {
    return new Response("Not Found", { status: 404 });
  }

  return new Response(`tiktok-developers-site-verification=${match[1]}`, {
    headers: {
      "Cache-Control": "public, max-age=300",
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
}
