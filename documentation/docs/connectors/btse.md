# BTSE.com Connector


## About BTSE.com

Our Mission is to use Bitcoin and digital asset technologies to build the suite of services that empowers you to take control of your financial freedom. Our Vision is the new financial standard built on the foundation of sound, immutable money. Our responsibility as an exchange is to provide the security and efficiency you need to confidently invest in your financial independence. Our passion is to do even more than that.


## Using the Connector

[Btse.com](https://www.btse.com/en/home) is a centralized exchange and you will need to connect your API keys to Hummingbot for trading.

```
Enter your Btse.com API key >>>
Enter your Btse.com secret key >>>
```

Private keys and API keys are stored locally for the operation of the Hummingbot client only. At no point will private or API keys be shared to Btse.com or be used in any way other than to authorize transactions required for the operation of Hummingbot.


### Creating Btse.com API keys

This help article below shows step-by-step instructions on how to create API keys in Btse exchange.

* [How do I create an API key?]

Private keys and API keys are stored locally for the operation of the Hummingbot client only. At no point will private or API keys be shared or be used in any way other than to authorize transactions required for the operation of Hummingbot.

!!! tip "Copying and pasting into Hummingbot"
    See [this page](/faq/troubleshooting/#paste-items-from-clipboard-in-putty) for more instructions in our Support section.


1 - Log into your Btse account, click your avatar and then select **API** (If you do not have an account, you will have to create one and verify your ID).


!!! tip "Important tip"
    You must enable 2FA in your BTSE account to create the API key. [How to enable 2FA?](https://support.btse.com/en/support/solutions/articles/43000061521-2fa-two-factor-authentication-)

2 - Click on **+ NEW API KEY**.

![btse1](/assets/img/btse_apikeys.png)

Make sure you give permissions to **View** and **Trade**, and enter your 2FA code. 

!!! warning "API key permissions"
    We recommend using only **"trade"** enabled API keys; enabling **"withdraw", "transfer", or the equivalent** is unnecessary for current Hummingbot strategies. In the event that for BTSE  **View** and **Trade** permissions are insufficient, select all 5 Key Restriction options for hummingbot trading as shown in the image.

Once you pass the authentication, you’ve created a new API Key!

Your API Secret will be displayed on the screen. Make sure you store your API Secret somewhere secure, and do not share it with anyone.

!!! warning
    If you lose your Secret Key, you can delete the API and create a new one. However, it will be impossible to reuse the same API.

## Miscellaneous Info

* [Security Tips](https://support.btse.com/en/support/solutions/articles/43000044048-security-tips)

### Minimum Order Sizes

The minimum order size for each trading pair is denominated in **base currency**. 

In the documentation you can also view minimum order limits:

* [Minimum Order Limits](https://support.btse.com/en/support/solutions/articles/43000533815)

For BTSE.Com, you can access the minimum order size for a specific token pair using the [BTSE.com API](https://www.btse.com/apiexplorer/spot/#getpublicmarketsummary)


### Transaction Fees

BTSE.com charges up to 0.1% on maker fees and 0.2% on taker fees with lower fees on using the BTSE token and depending on trading volume.

BTSE has account Specific fees, see their docs

Read through their help articles below for more information.

* [Spot Trading Fees](https://support.btse.com/en/support/solutions/articles/43000587197-spot-trading-fees)
* [API Docs](https://www.btse.com/apiexplorer/spot/#getfees)

Unlike other connectors, overriding the fee calculated by Hummingbot on trades by editing `conf_fee_overrides.yml` file will not be accurate but an estimate.

TBD --->> ?? Btse.com connector uses the trade info including the actual amount of fees paid. You can confirm this in the CSV file inside the `data` folder.
