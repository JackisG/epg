<!DOCTYPE html><html lang="en" data-bs-theme="dark"><head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>freeiptv</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">

        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="">
        <link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&amp;family=Montserrat:ital,wght@0,100..900;1,100..900&amp;display=swap" rel="stylesheet">

        <script src="https://cdn.jsdelivr.net/npm/iconify-icon@2.3.0/dist/iconify-icon.min.js"></script>
        
        <style>
            body {
                font-family: "Montserrat", serif;
                font-optical-sizing: auto;
                font-weight: 400;
                font-style: normal;
                margin-bottom: 4rem;
            }

            .title {
                background: #67B90E;
                background: linear-gradient(to right, #67B90E 0%, #1E80CF 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-weight: bold !important;
                font-size: 32px !important;
                -webkit-user-select: none; /* Safari */
                -ms-user-select: none; /* IE 10 and IE 11 */
                user-select: none; /* Standard syntax */
            }

            .content {
                text-align: center;
                margin-top: 3rem;
                margin-right: 12rem;
                margin-left: 12rem;
            }

            @media (max-width: 600px) {
                .content {
                    margin-right: 1rem;
                    margin-left: 1rem;
                }
            }
        </style>

        <script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"></script>
        <script>
            turnstile.ready(function() {
                turnstile.render("#freeiptv-turnstile", {
                    sitekey: "0x4AAAAAAA_Qtby-wpbozX7J",
                    callback: function(token) {
                        document.querySelector("#create-btn").disabled = false;
                        document.querySelector("#please-wait").style.display = "none";
                    },
                });
            });
        </script>
    </head>
  
    <body>
        <nav class="navbar bg-body-tertiary">
            <div class="container-fluid">
                <span class="navbar-brand mb-0 h1 title">freeiptv</span>
            </div>
        </nav>

        <div class="content">
            <h3>Free IPTV with 30,000+ channels</h3>

            

            <h5 class="mt-4" id="please-wait">Please wait 5 seconds for the button to get unlocked...</h5>

            <form method="POST" action="" class="mt-4">
                <div id="freeiptv-turnstile"><div><input type="hidden" name="cf-turnstile-response" id="cf-chl-widget-xvh0z_response" value=""></div></div>

                <input id="create-btn" disabled="" type="submit" class="btn btn-primary btn-lg" style="height: 8rem;" value="Create free IPTV account !">
            </form>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" crossorigin="anonymous"></script>
    <script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/v4513226cdae34746b4dedf0b4dfa099e1781791509496" integrity="sha512-ZE9pZaUXND66v380QUtch/5sE9tPFh2zg45pR2PB0CVkCtOREv2AJKkSidISWkysEuQ0EH8faUU5du78bx87UQ==" data-cf-beacon="{&quot;version&quot;:&quot;2024.11.0&quot;,&quot;token&quot;:&quot;815f97b2b9a34f8786208d343264dd8d&quot;,&quot;r&quot;:1}" crossorigin="anonymous"></script>

</body></html>