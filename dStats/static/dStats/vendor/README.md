# Bundled JavaScript libraries

Shipped with dStats so the dashboard works without internet access.
Both files keep their original license headers.

| File | Source | SHA-384 (base64) |
|---|---|---|
| `jquery-3.6.0.min.js` | https://code.jquery.com/jquery-3.6.0.min.js (MIT) | `vtXRMe3mGCbOeY7l30aIg8H9p3GdeSe4IFlP6G8JMa7o7lXvnz3GFKzPxzJdPfGK` |
| `cytoscape-3.30.4.min.js` | https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.4/cytoscape.min.js (MIT) | `H3uzGzTfGHUAumB8+s4GEdfFwzAceN9wCCndN8AXubWKFIPuBSWKKtWDx7RhSf/z` |

To update one: download the new version, check its hash against the publisher's
(`openssl dgst -sha384 -binary FILE | openssl base64 -A`), replace the file here, update
this table and the `{% static %}` path in `dStats/templates/dStats/index.html`.
