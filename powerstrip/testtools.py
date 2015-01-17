# Copyright ClusterHQ Limited. See LICENSE file for details.

"""
Test utilties for testing the proxy.
"""

from twisted.web import server, resource
import json


class FakeDockerServer(server.Site):
    def __init__(self, **kw):
        self.root = FakeDockerRoot(**kw)
        server.Site.__init__(self, self.root)


class FakeDockerRoot(resource.Resource):
    isLeaf = False
    def __init__(self, **kw):
        resource.Resource.__init__(self)
        self.putChild("towel", FakeDockerResource(**kw))


class FakeDockerResource(resource.Resource):
    isLeaf = True

    def __init__(self, rawStream=False, chunkedResponse=False):
        self.rawStream = rawStream
        self.chunkedResponse = chunkedResponse
        resource.Resource.__init__(self)

    def render_POST(self, request):
        """
        Take a JSON POST body, add an attribute to it "SeenByFakeDocker", then pass
        it back as a response.
        """
        jsonPayload = request.content.read()
        jsonParsed = json.loads(jsonPayload)
        if "SeenByFakeDocker" in jsonParsed:
            raise Exception("already seen by a fake docker?!")
        jsonParsed["SeenByFakeDocker"] = 42
        if not self.rawStream:
            request.setHeader("Content-Type", "application/json")
        else:
            request.setHeader("Content-Type", "application/vnd.docker.raw-stream")
        if self.chunkedResponse:
            request.setHeader("Content-Encoding", "chunked")
        return json.dumps(jsonParsed)


class AdderPlugin(server.Site):
    """
    The first powerstrip plugin: a pre-hook and post-hook implementation of a
    simple adder which can optionally blow up on demand.
    """
    def __init__(self, pre=False, post=False, explode=False, incrementBy=1):
        self.root = AdderRoot(pre, post, explode, incrementBy)
        server.Site.__init__(self, self.root)


class AdderResource(resource.Resource):
    isLeaf = True
    def __init__(self, pre, post, explode, incrementBy):
        self.pre = pre
        self.post = post
        self.explode = explode
        self.incrementBy = incrementBy
        resource.Resource.__init__(self)


    def _renderPreHook(self, request, jsonParsed):
        """
        Called with:

            POST /plugin HTTP/1.1
            Content-type: application/json
            Content-length: ...

            {
                Type: "pre-hook",
                Method: "POST",
                Request: "/v1.16/container/create",
                Body: { ... } or null
            }

        Responds with:

            HTTP 200 OK
            Content-type: application/json

            {
                Method: "POST",
                Request: "/v1.16/container/create",
                Body: { ... } or null,
            }

        """
        assert "Method" in jsonParsed
        assert "Request" in jsonParsed
        assert "Body" in jsonParsed
        print "*" * 80
        print "PRE HOOK"
        print "*" * 80
        jsonParsed["Body"]["Number"] += self.incrementBy
        request.setHeader("Content-Type", "application/json")
        return json.dumps(dict(Method="POST",
                               Request="/something",
                               Body=jsonParsed["Body"]))


    def _renderPostHook(self, request, jsonParsed):
        """
        Called with:

            POST /plugin HTTP/1.1

            {
                Type: "post-hook",
                OriginalMethod: "POST",
                OriginalRequest: "/v1.16/containers/create",
                OriginalBody: { ... },
                DockerResponseContentType: "text/plain",
                DockerResponseBody: { ... } (if application/json)
                                    or "not found" (if text/plain)
                                    or null (if it was a GET request),
                DockerResponseCode: 404,
            }

        Responds with:

            {
                ContentType: "application/json",
                Body: { ... },
                Code: 200,
            }
        """
        print "*" * 80
        print "POST HOOK"
        print "*" * 80
        assert "OriginalMethod" in jsonParsed
        assert "OriginalRequest" in jsonParsed
        assert "OriginalBody" in jsonParsed
        assert "DockerResponseContentType" in jsonParsed
        jsonParsed["DockerResponseBody"]["Number"] += self.incrementBy
        assert "DockerResponseCode" in jsonParsed
        request.setHeader("Content-Type", "application/json")
        return json.dumps(dict(ContentType="application/json",
                               Body=jsonParsed["DockerResponseBody"],
                               Code=200))

    def render_POST(self, request):
        """
        OK, we got to the meat of it.

        This render handles JSON POST requests.

        If pre is set, it succeeds on JSON which looks like.
            Type: "pre-hook"

        If post is set, it succeeds on JSON which looks like.
            Type: "post-hook"

        If explode is set, it always returns a 500 error.
        """
        print "*" * 80
        print "DOCKER API"
        print "*" * 80
        jsonPayload = request.content.read()
        jsonParsed = json.loads(jsonPayload)

        if self.explode:
            request.setResponseCode(500)
            return "sadness for you, today."

        if jsonParsed["Type"] == "pre-hook" and self.pre:
            return self._renderPreHook(request, jsonParsed)
        elif jsonParsed["Type"] == "post-hook" and self.post:
            return self._renderPostHook(request, jsonParsed)


class AdderRoot(resource.Resource):
    isLeaf = False
    def __init__(self, pre, post, explode, incrementBy):
        self.pre = pre
        self.post = post
        self.explode = explode
        self.incrementBy = incrementBy
        resource.Resource.__init__(self)
        self.putChild("plugin", AdderResource(self.pre, self.post, self.explode, self.incrementBy))
