from fasthtml.common import *


def _legal_section(title: str, *content):
    return Section(
        H2(title, cls='text-xl font-semibold text-black mb-3'),
        *content,
        cls='mb-8',
    )


def _paragraph(text: str):
    return P(text, cls='text-sm leading-7 text-gray-600 mb-3')


def privacy_page():
    return Div(
        Section(
            Div(
                H1('Privacy Policy', cls='font-display text-4xl font-extrabold text-black mb-4'),
                P('Last updated: 3 September 2026', cls='text-sm text-gray-500'),
                cls='max-w-4xl mx-auto',
            ),
            cls='bg-white py-16 px-8',
        ),
        Section(
            Div(
                _legal_section(
                    'Who we are',
                    _paragraph(
                        'CarHero is operated by Predictive Labs Ltd (company number 14857334), '
                        '155 Minories Street, Suite 275, London, EC3N 1AD, United Kingdom. '
                        'For privacy questions, contact info@carhero.chat.'
                    ),
                ),
                _legal_section(
                    'Information we collect',
                    Ul(
                        Li('Account information, including your name, email address, account identifier and authentication information.'),
                        Li('Optional profile and preference information, such as phone number, country, city, language, currency, vehicle preferences and budget.'),
                        Li('Content and activity, including AI chat prompts and responses, saved searches, favourites, notes, shared-chat choices and contact messages.'),
                        Li('Garage information you choose to provide, such as vehicle details, mileage, purchase date, purchase price and ownership-cost inputs.'),
                        Li('Technical information needed to operate and secure the service, such as IP address, request time, device or browser information and error logs.'),
                        cls='list-disc pl-6 text-sm leading-7 text-gray-600 space-y-2',
                    ),
                ),
                _legal_section(
                    'How we use information',
                    _paragraph(
                        'We use this information to create and secure your account; provide search, '
                        'comparison, valuation, AI-advisory and garage features; remember your choices; '
                        'send requested service messages; respond to support requests; prevent abuse; '
                        'and improve the reliability and safety of CarHero.'
                    ),
                ),
                _legal_section(
                    'AI and service providers',
                    _paragraph(
                        'Prompts and relevant conversation context may be sent to contracted AI service '
                        'providers, including OpenAI or xAI, to generate CarHero responses. Google processes '
                        'information when you use Google Sign-In, and Postmark processes contact details '
                        'needed to deliver transactional email. Hosting, database and security providers '
                        'process information on our behalf to operate CarHero.'
                    ),
                    _paragraph(
                        'We do not sell personal information. We may disclose information when required by '
                        'law, to protect users or the service, or as part of a corporate transaction subject '
                        'to appropriate safeguards.'
                    ),
                ),
                _legal_section(
                    'Legal bases and international transfers',
                    _paragraph(
                        'Where UK or European data-protection law applies, we process information to provide '
                        'the service you request, based on our legitimate interests in operating and securing '
                        'CarHero, to comply with legal obligations, and with consent where required. Some '
                        'providers may process information outside your country; we use contractual and other '
                        'lawful safeguards where required.'
                    ),
                ),
                _legal_section(
                    'Retention and deletion',
                    _paragraph(
                        'We retain account information and saved content while your account is active and as '
                        'needed to provide CarHero, meet legal obligations, resolve disputes and prevent abuse. '
                        'You can permanently delete your account and associated saved data from Profile & '
                        'Preferences in the app. You can also request deletion on our account-deletion page. '
                        'Residual copies may remain in protected backups until their normal rotation.'
                    ),
                    A('Request account deletion', href='/delete-account',
                      cls='inline-flex items-center px-4 py-2 rounded-full text-sm font-medium bg-black text-white no-underline hover:bg-gray-800'),
                ),
                _legal_section(
                    'Your choices and rights',
                    _paragraph(
                        'You can update profile information in the app and control optional notification '
                        'preferences. Depending on where you live, you may have rights to access, correct, '
                        'delete, restrict or object to processing, request portability, or complain to a '
                        'data-protection authority. Contact info@carhero.chat to exercise these rights.'
                    ),
                ),
                _legal_section(
                    'Security and children',
                    _paragraph(
                        'We use technical and organisational safeguards designed to protect information, '
                        'including encrypted network connections and access controls. No online service is '
                        'completely secure. CarHero is intended for adults aged 18 and over and is not directed '
                        'to children.'
                    ),
                ),
                _legal_section(
                    'Changes to this policy',
                    _paragraph(
                        'We may update this policy as CarHero or legal requirements change. We will publish '
                        'the updated version here and revise the date above.'
                    ),
                ),
                cls='max-w-4xl mx-auto',
            ),
            cls='py-16 px-8 bg-gray-50',
        ),
    )


def delete_account_page():
    return Div(
        Section(
            Div(
                H1('Delete your CarHero account', cls='font-display text-4xl font-extrabold text-black mb-4'),
                P('Permanently remove your account and associated saved data.', cls='text-lg text-gray-500'),
                cls='max-w-4xl mx-auto',
            ),
            cls='bg-white py-16 px-8',
        ),
        Section(
            Div(
                H2('Delete in the app', cls='text-xl font-semibold text-black mb-3'),
                Ol(
                    Li('Open CarHero and sign in.'),
                    Li('Open the menu and select Profile.'),
                    Li('Scroll to Delete account and confirm permanent deletion.'),
                    cls='list-decimal pl-6 text-sm leading-7 text-gray-600 space-y-2 mb-8',
                ),
                H2('Request deletion without the app', cls='text-xl font-semibold text-black mb-3'),
                _paragraph(
                    'Email us from the address registered to your CarHero account. We will verify the request '
                    'before deleting the account and associated chat history, favourites, saved searches, '
                    'garage vehicles and profile preferences.'
                ),
                A('Email an account-deletion request',
                  href='mailto:info@carhero.chat?subject=CarHero%20account%20deletion%20request',
                  cls='inline-flex items-center px-4 py-2 rounded-full text-sm font-medium bg-black text-white no-underline hover:bg-gray-800'),
                P('We may retain information required by law and residual copies in protected backups until normal rotation.',
                  cls='text-xs leading-6 text-gray-500 mt-6'),
                cls='max-w-3xl mx-auto bg-white border border-gray-200 rounded-xl p-8',
            ),
            cls='py-16 px-8 bg-gray-50',
        ),
    )
