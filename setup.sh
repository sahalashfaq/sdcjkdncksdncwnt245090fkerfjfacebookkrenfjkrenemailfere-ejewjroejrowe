#!/bin/bash

# Download matching ChromeDriver version 120
CHROMEDRIVER_VERSION=120.0.6099.109

curl -SL https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip -o chromedriver.zip
unzip chromedriver.zip
mv chromedriver-linux64/chromedriver /usr/bin/chromedriver
chmod +x /usr/bin/chromedriver
