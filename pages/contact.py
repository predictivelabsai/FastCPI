from fasthtml.common import *


INPUT_CLS = 'w-full px-3 py-2 border border-gray-200 rounded-md text-sm mb-4 font-sans'


def contact_page():
    return Div(
        Section(
            Div(
                H1('Contact Us', cls='font-display text-4xl font-extrabold text-black mb-4'),
                P('Questions or feedback? We would love to hear from you.',
                  cls='text-lg text-gray-500'),
                cls='max-w-7xl mx-auto relative z-10'
            ),
            cls='bg-white py-16 px-8'
        ),
        Section(
            Div(
                Div(
                    Form(
                        Div(
                            Label('Name', cls='block mb-1 font-semibold text-sm text-gray-900'),
                            Input(type='text', name='name', placeholder='Your name', cls=INPUT_CLS),
                        ),
                        Div(
                            Label('Email', cls='block mb-1 font-semibold text-sm text-gray-900'),
                            Input(type='email', name='email', placeholder='you@example.com', cls=INPUT_CLS),
                        ),
                        Div(
                            Label('Message', cls='block mb-1 font-semibold text-sm text-gray-900'),
                            Textarea(name='message', placeholder='Your message...', rows=5,
                                     cls=INPUT_CLS + ' resize-none'),
                        ),
                        Button('Send Message', type='submit',
                               cls='w-full mt-2 px-6 py-2.5 rounded-full font-semibold text-sm bg-black text-white hover:bg-gray-800 transition-colors cursor-pointer border-none'),
                        method='post', action='/contact',
                        cls='bg-white p-8 rounded-lg shadow-sm max-w-md mx-auto'
                    ),
                    cls='max-w-7xl mx-auto'
                ),
            ),
            cls='py-20 px-8 bg-gray-50'
        ),
    )
