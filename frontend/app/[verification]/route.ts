const VERIFICATION_FILE = "tiktokYiYmxWvT4YcoPaT72exrsOcPmWJagL9I.txt";
const VERIFICATION_BODY = "tiktok-developers-site-verification=YiYmxWvT4YcoPaT72exrsOcPmWJagL9I";

export function GET(
  _request: Request,
  { params }: { params: { verification: string } },
) {
  if (params.verification !== VERIFICATION_FILE) {
    return new Response("Not Found", { status: 404 });
  }

  return new Response(VERIFICATION_BODY, {
    headers: {
      "Cache-Control": "public, max-age=300",
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
}
