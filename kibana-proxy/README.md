1. Generate a server certificate and key.

```
    sudo mkdir -p /etc/pki/nginx/private
    sudo openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 -keyout /etc/pki/nginx/private/server.key -out /etc/pki/nginx/server.crt
```

1. Install aws-es-proxy binary.

```
   wget https://github.com/abutaha/aws-es-proxy/releases/download/v0.9/aws-es-proxy-0.9-linux-386
```

1. Install nginx.

```
sudo yum install -y nginx
```

1. Configure nginx in `/etc/nginx/nginx.conf`:

```
    server {
        listen       80 default_server;
        listen       [::]:80 default_server;
        server_name  _;
        return 301 https://$host$request_uri;
    }

    server {
        listen       443 ssl http2 default_server;
        listen       [::]:443 ssl http2 default_server;
        server_name  _;
        root         /usr/share/nginx/html;

        ssl_certificate "/etc/pki/nginx/server.crt";
        ssl_certificate_key "/etc/pki/nginx/private/server.key";
        ssl_session_cache shared:SSL:1m;
        ssl_session_timeout  10m;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        # Load configuration files for the default server block.
        include /etc/nginx/default.d/*.conf;

        location / {
            proxy_pass http://localhost:9200;
        }

        error_page 404 /404.html;
            location = /40x.html {
        }

        error_page 500 502 503 504 /50x.html;
            location = /50x.html {
        }
    }

```

1. Start nginx.

```
sudo systemctl enable nginx
sudo systemctl start nginx
```

1. Start aws-es-proxy (need to know ES endpoint URL).

```
   ./aws-es-proxy-0.9-linux-386 -endpoint \$ELASTICSEARCH_ENDPOINT -no-sign-reqs -listen 0.0.0.0:9200
```
