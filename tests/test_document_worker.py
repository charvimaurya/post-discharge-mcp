from lambdas.document_processor.handler import (
    lambda_handler,
)

def test_handler_accepts_empty_event():

    result = lambda_handler(
        {
            "Records": []
        },
        None,
    )

    assert result == {
        "batchItemFailures": []
    }