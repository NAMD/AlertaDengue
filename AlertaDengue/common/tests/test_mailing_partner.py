import unittest
from common.models import SendToPartner
from django.core import mail


class SendToPartnerTest(unittest.TestCase):
    """
    Tests login the django admin interface
    """

    databases = ['infodengue', 'default']
    fixtures = ['AlertaDengue/common/fixtures/users.json']

    def create_partner(self):
        return SendToPartner.objects.create(
            geocode=3304557,
            name="Rio de Janeiro",
            abbreviation="RJ",
            level="Municipal",
            contact="sec.test@gov.br",
            status=True,
        )

    def test_create_partner(self):
        partner = self.create_partner()
        self.assertEqual(partner.geocode, 3304557)
        self.assertEqual(partner.name, "Rio de Janeiro")
        self.assertEqual(partner.abbreviation, "RJ")
        self.assertEqual(partner.level, 'Municipal')
        self.assertEqual(partner.contact, 'sec.test@gov.br')

    def test_send_mail(self):
        partner = self.create_partner()
        week = '02'
        mail_from = 'info_dengue@gmail.com'
        mail_text = 'Here is the message.'
        mail_subject = f'Informe de dados Infodengue SE {week}'
        mail_to = str(partner.contact)
        mail.send_mail(
            mail_subject, mail_text, mail_from, [mail_to], fail_silently=False,
        )

        # Test that one message has been sent.
        self.assertEqual(len(mail.outbox), 1)

        # Verify that the subject of the first message is correct.
        self.assertEqual(
            mail.outbox[0].subject, f'Informe de dados Infodengue SE {week}'
        )
        self.assertEqual(partner.name, 'Rio de Janeiro')