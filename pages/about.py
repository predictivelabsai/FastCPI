from fasthtml.common import *


def about_page():
    return Div(
        Section(
            Div(
                H1('About CarHero', cls='font-display text-4xl font-extrabold text-black mb-4'),
                P('AI-powered car advisory for the European premium market.',
                  cls='text-lg text-gray-500'),
                cls='max-w-7xl mx-auto relative z-10'
            ),
            cls='bg-white py-16 px-8'
        ),
        Section(
            Div(
                Div(
                    H2('What we do', cls='text-2xl font-medium text-black mb-4'),
                    P('CarHero helps car buyers across Europe find, compare, and value premium vehicles. '
                      'We aggregate listings from AutoTrader UK, mobile.de, AutoScout24, and Autohero, '
                      'covering BMW, Mercedes-Benz, Audi, Porsche, Jaguar, Land Rover, Volvo, Tesla, and Lexus.',
                      cls='text-gray-500 text-sm leading-relaxed mb-6'),
                    H2('How it works', cls='text-2xl font-medium text-black mb-4'),
                    P('Our AI agents analyze thousands of real listings to provide fair market valuations, '
                      'depreciation insights, and personalized buying recommendations. '
                      'Whether you are comparing a BMW X5 in Germany vs the UK, or tracking price trends '
                      'for a specific model, CarHero gives you the data to decide with confidence.',
                      cls='text-gray-500 text-sm leading-relaxed mb-6'),
                    H2('Technology', cls='text-2xl font-medium text-black mb-4'),
                    P('Built with AI agents powered by large language models, real-time web scraping, '
                      'and interactive data visualizations. We support 12 languages across our European platform.',
                      cls='text-gray-500 text-sm leading-relaxed'),
                    cls='max-w-3xl mx-auto'
                ),
                cls='max-w-7xl mx-auto'
            ),
            cls='py-20 px-8 bg-gray-50'
        ),
    )
