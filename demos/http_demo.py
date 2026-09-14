"""SmallOS HTTP example using the native cooperative HTTP client."""

from common import build_runtime

from SmallPackage import SmallHTTPClient, SmallTask, Unix


HTTP_BASE_URL = "http://example.com"


async def http_demo(task):
    # Passing the attached task lets the client inherit transport limits from
    # task.OS.config and suspend on this runtime's kernel readiness operations.
    client = SmallHTTPClient(task, base_url=HTTP_BASE_URL)
    # While connect/send/receive waits for the socket, other smallOS tasks may run.
    response = await client.get("/", headers={"Accept": "text/html"})
    preview = response.text().replace("\n", " ")[:120]
    task.OS.print("http status: {} {}\n".format(response.status_code, response.reason))
    task.OS.print("http preview: {}\n".format(preview))
    return response.status_code


def main():
    runtime = build_runtime(Unix())
    # Priority 2 is a scheduler category; lower numeric categories run first.
    runtime.fork([SmallTask(2, http_demo, name="http_demo")])
    runtime.startOS()


if __name__ == "__main__":
    main()
