import logging
import os
from datetime import date

import requests

from bolletta_sync.providers.base_provider import BaseProvider, Invoice

logger = logging.getLogger(__name__)


class UmbraAcque(BaseProvider):
    def __init__(self, google_credentials, solver):
        super().__init__(google_credentials, logger, "umbra_acque")
        self._solver = solver
        self._session = requests.Session()

    async def _login_umbra_acque(self):
        self._session.cookies.clear()

        try:
            result = self._solver.recaptcha(
                sitekey="6LcO28gqAAAAAATkRJuvOZI41YhfX9u-jwWs_14N",
                url="https://self-service.umbraacque.com/umbraacque/login",
                version="v3")

            payload = {
                "loginID": os.getenv("UMBRA_ACQUE_USERNAME"),
                "password": os.getenv("UMBRA_ACQUE_PASSWORD"),
                "sessionExpiration": "43200",
                "targetEnv": "jssdk",
                "include": "profile,data,emails,subscriptions,preferences,id_token,",
                "includeUserInfo": "true",
                "captchaToken": result["code"],
                "captchaType": "reCaptchaV3",
                "loginMode": "standard",
                "lang": "it",
                "riskContext": '{"b0":29525,"b1":[28,24,46,46],"b2":4,"b3":[],"b4":1,"b5":1,"b6":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36","b7":[{"name":"PDF Viewer","filename":"internal-pdf-viewer","length":2},{"name":"Chrome PDF Viewer","filename":"internal-pdf-viewer","length":2},{"name":"Chromium PDF Viewer","filename":"internal-pdf-viewer","length":2},{"name":"Microsoft Edge PDF Viewer","filename":"internal-pdf-viewer","length":2},{"name":"WebKit built-in PDF","filename":"internal-pdf-viewer","length":2}],"b8":"1:22:51 AM","b9":-120,"b10":{"state":"prompt"},"b11":false,"b12":{"charging":false,"chargingTime":null,"dischargingTime":3523,"level":0.18},"b13":[null,"1920|1200|24",false,true]}',
                "APIKey": "3_aWk59TWdmbA3d6nkOuNTblzJyaIwZTUSVzLsMoK5_L3zPip_Om9NAjg1uDQifCbT",
                "source": "showScreenSet",
                "sdk": "js_latest",
                "authMode": "cookie",
                "pageURL": "https://self-service.umbraacque.com/umbraacque/login",
                "sdkBuild": "17992",
                "format": "json"
            }
            self._session.cookies.set("gmid",
                                      "gmid.ver4.AtLtRQ5UsA.H9yJP4mqvoA2ujdImqLGnlaxX-ZJkTmS1nseFwU-NvJynNh3h1ErVXkujEdU_Ozz.ptb9nP0pNoPkAsWmg9_dXOAY-yIi5I0cMpTwc_hfXhiMizUMwR0Y3sGVa1s7sTXyTmM82uF0aADVCQGb4LEoxw.sc3")
            response = self._session.post(
                "https://accounts.eu1.gigya.com/accounts.login",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response_body = dict(response.json())
            if response_body.get("errorCode") != 0 or "sessionInfo" not in response_body:
                raise Exception()
            session_info = response_body["sessionInfo"]
            self._session.cookies.set("login_token", session_info["login_token"])

        except Exception as e:
            logger.error(e)
            raise Exception("login failed")

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_umbra_acque()

        response = self._session.get("https://self-service.umbraacque.com/bin/acea-myacea/utenze", params={
            "path": "/content/acea-myacea/umbraacque/selfcare/privato"})
        response.raise_for_status()
        contract_pk = response.json().get("data")[0]["contractPk"]

        response = self._session.get(
            "https://self-service.umbraacque.com/bin/acea-myacea/invoicesAndBalance",
            params={
                "path": "/content/acea-myacea/umbraacque/selfcare/fatture/jcr:content/content-private-par/invoices_table",
                "contractPk": contract_pk
            }
        )
        response.raise_for_status()
        invoice_list = list(
            map(lambda i: Invoice(id=i["invoiceNumber"], doc_date=i["issueDate"], due_date=i["expiryDate"],
                                  amount=i["total"], client_code=i["contractId"]),
                response.json().get("body")["invoices"]))
        invoice_list_filtered = list(
            filter(lambda invoice: start_date <= invoice.doc_date <= end_date, invoice_list))
        if invoice_list_filtered:
            invoices.extend(invoice_list_filtered)

        return invoices

    async def download_invoice(self, invoice: Invoice) -> bytes:
        return b""

    async def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        result = await super().save_invoice(invoice, invoice_pdf)
        return result

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        result = await super().set_expire_invoice(invoice)
        return result
