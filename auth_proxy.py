#!/usr/bin/env python3
"""OAuth redirect helper for Bosch Indego integration.

This small web server captures the OAuth callback from Bosch SingleKey ID and
forwards it to Home Assistant. Run this script and open the printed URL in your
browser to authenticate without the Chrome extension.
"""
import http.server
import socketserver
import urllib.parse
import webbrowser

PORT = 8765

class OAuthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        if "code=" in query:
            ha_url = "https://my.home-assistant.io/redirect/oauth?" + query
            self.send_response(302)
            self.send_header("Location", ha_url)
            self.end_headers()
            print("Forwarding to Home Assistant:", ha_url)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")


def main():
    url = (
        "https://prodindego.b2clogin.com/prodindego.onmicrosoft.com/"
        "b2c_1a_signup_signin/oauth2/v2.0/authorize?redirect_uri=http://localhost:%d"
        % PORT
    )
    with socketserver.TCPServer(("localhost", PORT), OAuthHandler) as httpd:
        print(f"Open the following URL in your browser:\n{url}")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Stopping server")

if __name__ == "__main__":
    main()
