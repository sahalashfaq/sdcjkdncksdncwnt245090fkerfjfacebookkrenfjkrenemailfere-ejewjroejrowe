#!/bin/bash

# Required version
CHROMEDRIVER_VERSION=120.0.6099.109

# Download ChromeDriver for Chrome 120
curl -SL "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" -o chromedriver.zip
unzip chromedriver.zip
mv chromedriver-linux64/chromedriver /usr/bin/chromedriver
chmod +x /usr/bin/chromedriver
