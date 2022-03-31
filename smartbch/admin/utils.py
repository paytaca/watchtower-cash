import decimal
from django.contrib import admin, messages


class InputFilter(admin.SimpleListFilter):
    template = "admin/input_filter.html"

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)
        self.request = request

    def lookups(self, request, model_admin):
        # Dummy, required to show the filter.
        return ((),)

    def choices(self, changelist):
        # Grab only the "all" option.
        all_choice = next(super().choices(changelist))
        all_choice['query_parts'] = (
            (k, v)
            for k, v in changelist.get_filters_params().items()
            if k != self.parameter_name
        )

        yield all_choice
        

class BlockRangeFilter(admin.ListFilter):
    template = "admin/block_range_filter.html"
    title = "Block Range"

    BEFORE_BLOCK_PARAMETER_NAME = "before_block"
    AFTER_BLOCK_PARAMETER_NAME = "after_block"

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)

        self.used_parameters = {}
        self.use_parameter(params, self.BEFORE_BLOCK_PARAMETER_NAME)
        self.use_parameter(params, self.AFTER_BLOCK_PARAMETER_NAME)

        self.lookup_choices = []


    def use_parameter(self, params, param_name):
        if not self.used_parameters:
            self.used_parameters = {}

        if param_name in params:
            value = params.pop(param_name)
            self.used_parameters[param_name] = value
            return value

    # Needed for parent class
    def has_output(self):
        return True

    # Needed for parent class
    def expected_parameters(self):
        return [
            self.BEFORE_BLOCK_PARAMETER_NAME,
            self.AFTER_BLOCK_PARAMETER_NAME,
        ]

    # Needed for parent class
    def choices(self, changelist):
        yield {
            "selected": True,
            "query_string": changelist.get_query_string(),
            "display": "All",
        }


    def before_value(self):
        if self.BEFORE_BLOCK_PARAMETER_NAME in self.used_parameters:
            try:
                return decimal.Decimal(self.used_parameters[self.BEFORE_BLOCK_PARAMETER_NAME])
            except decimal.InvalidOperation:
                pass

    def after_value(self):
        if self.AFTER_BLOCK_PARAMETER_NAME in self.used_parameters:
            try:
                return decimal.Decimal(self.used_parameters[self.AFTER_BLOCK_PARAMETER_NAME])
            except decimal.InvalidOperation:
                pass
